import torch
import torch.nn as nn
from torch.distributions import Categorical, Normal

class PointNetEncoder(nn.Module):
    def __init__(self, output_dim: int, input_dim: int = 6):
        """모기의 각 축별 위치 좌표와 속도 벡터를 입력으로 받는다 (x,y,z,vx,vy,vz)"""
        super().__init__()
        self.output_dim = output_dim
        self.mlp = nn.Sequential(
            nn.Linear(input_dim, 64), nn.ReLU(),
            nn.Linear(64, 128), nn.ReLU(),
            nn.Linear(128, output_dim)
        )

    def forward(self, points: torch.Tensor):
        if points.shape[1] == 0:
            raise ValueError("There is no Buffer Sensor")

        mask = points.abs().sum(dim=-1) > 0
        x: torch.Tensor = self.mlp(points)
        x = x.masked_fill(~mask.unsqueeze(-1), float("-inf")) # max pooling울 위해 -inf 삽입
        x = x.max(dim=1).values
        x = torch.where(torch.isinf(x), torch.zeros_like(x), x)
        return x

class ActorCritic(nn.Module):
    def __init__(
        self,
        observation_dim: int,
        pointnet_out_dim: int,
        continuous_dim: int,
        discrete_sizes: list[int]
    ):
        super().__init__()
        self.observation_encoder = nn.Sequential(
            nn.Linear(observation_dim, 64), nn.Tanh(), # 값이 무한대로 발산하지 못하도록 Tanh 사용
            nn.Linear(64, 64), nn.Tanh(),
        )
        self.pointnet = PointNetEncoder(output_dim=pointnet_out_dim)
        # 두 encoder의 출력을 결합하여 Actor와 Critic의 input으로 사용
        self.fusion = nn.Sequential(nn.Linear(64 + pointnet_out_dim, 128), nn.Tanh())

        # Actor
        self.continuous_mean = nn.Linear(128, continuous_dim) # Continous Action predict
        self.log_std = nn.Parameter(torch.zeros(continuous_dim))
        self.discrete_heads = nn.ModuleList([nn.Linear(128, s) for s in discrete_sizes]) # 어떤 행동을 할지 Logits 출력

        #Critic
        self.value_head = nn.Linear(128, 1)

    def _encode(self, observation_vector: torch.Tensor, point_cloud: torch.Tensor):
        """관측 벡터와 포인트 클라우드를 각각 인코딩한 뒤 결합해 128차원 히든 벡터로 반환"""
        hidden_observation_vector = self.observation_encoder(observation_vector)
        hidden_point_cloud = self.pointnet(point_cloud)
        hidden_vector = self.fusion(torch.cat([hidden_observation_vector,hidden_point_cloud], dim=1))
        return hidden_vector

    def get_action(self, observation_vector: torch.Tensor, point_cloud: torch.Tensor):
        """행동 샘플링. pre-tanh u 도 함께 반환 — 버퍼에 u 를 저장해야
        evaluate 에서 atanh 역연산 없이 정확한 log_prob 재계산 가능 (경계 ratio spike 방지)"""
        hidden_vector = self._encode(observation_vector, point_cloud)

        # Continous: tanh-squashed Gaussian
        mean = self.continuous_mean(hidden_vector)
        std = self.log_std.clamp(-2.0, 0.5).exp().expand_as(mean)  
        continuous_dist = Normal(mean, std)
        u = continuous_dist.rsample() # Gaussian sampling, rsample써야 미분 가능 sample x
        continuous_action = torch.tanh(u)
        log_prob = continuous_dist.log_prob(u).sum(-1) - torch.log(1.0 - continuous_action.pow(2) + 1e-6).sum(-1)

        # Discrete
        discrete_list = []

        for head in self.discrete_heads:
            discrete_dist = Categorical(logits=head(hidden_vector))
            discrete_action = discrete_dist.sample()
            log_prob = log_prob + discrete_dist.log_prob(discrete_action)
            discrete_list.append(discrete_action)

        discrete_action_tensor = torch.stack(discrete_list, dim=-1)

        value = self.value_head(hidden_vector).squeeze(-1) # Expected Return

        return continuous_action, u, discrete_action_tensor, log_prob, value

    def evaluate(
        self,
        observation_vector: torch.Tensor,
        point_cloud: torch.Tensor,
        pre_tanh_action: torch.Tensor,
        discrete_action: torch.Tensor
    ):
        """수집 시 저장한 pre-tanh u 를 그대로 사용. atanh(clamp(tanh(u))) 복원 경로는
        경계(±1)에서 수치 오차로 log_prob 이 튀어 PPO ratio 가 폭주할 수 있음"""
        hidden_vector = self._encode(observation_vector, point_cloud)

        # Continuous
        mean = self.continuous_mean(hidden_vector)
        std = self.log_std.clamp(-2.0, 0.5).exp().expand_as(mean)  # 상한 0.5 -> std<=1.65, entropy 폭주 차단
        continuous_dist = Normal(mean, std)

        squashed = torch.tanh(pre_tanh_action)
        log_prob = continuous_dist.log_prob(pre_tanh_action).sum(-1) - torch.log(1.0 - squashed.pow(2) + 1e-6).sum(-1)
        # entropy 를 연속/이산으로 분리해 반환 — 단일 합산 시 H_cont(4차원)가 H_disc(≤log2)를
        # 압도해 발사/대기 탐색 유지 인센티브가 사실상 사라짐
        entropy_continuous = continuous_dist.entropy().sum(-1)

        # Discrete
        entropy_discrete = torch.zeros_like(entropy_continuous)
        for i, head in enumerate(self.discrete_heads):
            discrete_dist = Categorical(logits=head(hidden_vector))
            log_prob = log_prob + discrete_dist.log_prob(discrete_action[:, i])
            entropy_discrete = entropy_discrete + discrete_dist.entropy()

        value = self.value_head(hidden_vector).squeeze(-1)
        return log_prob, entropy_continuous, entropy_discrete, value

    def get_value(self, observation_vector: torch.Tensor, point_cloud: torch.Tensor):
        hidden_vector = self._encode(observation_vector, point_cloud)
        return self.value_head(hidden_vector).squeeze(-1)

    def get_deterministic_action(self, observation_vector: torch.Tensor, point_cloud: torch.Tensor):
        """평가용 결정론 행동 — 연속은 분포 평균, 이산은 최대 확률 선택 (탐색 노이즈 없음)"""
        hidden_vector = self._encode(observation_vector, point_cloud)
        continuous_action = torch.tanh(self.continuous_mean(hidden_vector))
        discrete_list = [head(hidden_vector).argmax(dim=-1) for head in self.discrete_heads]
        discrete_action_tensor = torch.stack(discrete_list, dim=-1)
        return continuous_action, discrete_action_tensor
