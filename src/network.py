import torch
import torch.nn as nn
from torch.distributions import Normal, Categorical


class PointNetEncoder(nn.Module):
    """
    Args:
        out_dim: 출력 특징 벡터 차원. ActorCritic의 pointnet_out과 일치해야 함.
        in_dim: 모기 1마리당 입력 피처 수. 위치(x,y,z) + 속도(vx,vy,vz) = 6.
    """
    def __init__(self, out_dim: int, in_dim: int = 6):
        super().__init__()
        self.out_dim = out_dim
        self.mlp = nn.Sequential(
            nn.Linear(in_dim, 64),
            nn.ReLU(),
            nn.Linear(64, 128),
            nn.ReLU(),
            nn.Linear(128, out_dim)
        )

    def forward(self, points: torch.Tensor) -> torch.Tensor:
        """
        Args:
            points: 모기 포인트 집합. shape [B, N, in_dim]. N은 BufferSensor 최대치(패딩 포함).
                    전부 0인 행은 모기가 없는 패딩으로 간주.
        Returns:
            shape [B, out_dim]. 감지된 모기가 없으면 zeros 반환.
        """
        # points: [B, N, 6]
        if points.shape[1] == 0:  # BufferSensor가 없거나 빈 경우
            return torch.zeros(points.shape[0], self.out_dim, device=points.device)

        # 패딩 마스크: 하나라도 0이 아닌 행 = 실제 모기
        mask = points.abs().sum(dim=-1) > 0           # [B, N]

        x = self.mlp(points)                          # [B, N, out_dim]
        # 패딩 위치를 -inf로 채워 Max Pooling에서 제외
        x = x.masked_fill(~mask.unsqueeze(-1), float("-inf"))
        x = x.max(dim=1).values                       # [B, out_dim]
        # 감지된 모기가 하나도 없는 샘플(전 행 패딩)은 -inf → 0으로 치환
        x = torch.where(torch.isinf(x), torch.zeros_like(x), x)
        return x


class ActorCritic(nn.Module):
    """
    Args:
        vec_dim: 벡터 관측 차원. CollectObservations에서 AddObservation 호출 횟수와 일치해야 함.
        pointnet_out: PointNetEncoder 출력 차원. fusion 입력 크기(64 + pointnet_out)에 영향.
        cont_dim: 연속 행동 수. Behavior Parameters의 Continuous Actions 값과 일치해야 함.
        disc_sizes: 이산 행동 브랜치별 선택지 수. e.g. [2] = 브랜치 1개, 선택지 2개(대기/공격).
    """
    def __init__(self, vec_dim: int, pointnet_out: int, cont_dim: int, disc_sizes: list[int]):
        super().__init__()

        # 벡터 관측 인코더
        self.vec_encoder = nn.Sequential(
            nn.Linear(vec_dim, 64),
            nn.Tanh(),
            nn.Linear(64, 64),
            nn.Tanh()
        )

        self.pointnet = PointNetEncoder(out_dim=pointnet_out)

        # 융합 레이어
        self.fusion = nn.Sequential(
            nn.Linear(64 + pointnet_out, 128), nn.Tanh(),
        )

        # Actor — 연속 행동: Gaussian
        self.cont_mean = nn.Linear(128, cont_dim)
        self.log_std   = nn.Parameter(torch.zeros(cont_dim))  # 학습 가능한 표준편차

        # Actor — 이산 행동: Categorical (브랜치별)
        self.disc_heads = nn.ModuleList([nn.Linear(128, s) for s in disc_sizes])

        # Critic
        self.value_head = nn.Linear(128, 1)

    def _encode(self, vec_obs: torch.Tensor, point_cloud: torch.Tensor) -> torch.Tensor:
        """
        Args:
            vec_obs: 벡터 관측. shape [B, vec_dim].
            point_cloud: 모기 포인트 집합. shape [B, N, in_dim].
        Returns:
            융합된 특징 벡터. shape [B, 128].
        """
        h_vec = self.vec_encoder(vec_obs) # [B, 64]
        h_pt = self.pointnet(point_cloud) # [B, pointnet_out]
        h = self.fusion(torch.cat([h_vec, h_pt], dim=-1)) # [B, 128]
        return h

    def get_action(self, vec_obs: torch.Tensor, point_cloud: torch.Tensor):
        """
        Args:
            vec_obs: 벡터 관측. shape [B, vec_dim].
            point_cloud: 모기 포인트 집합. shape [B, N, in_dim].
        Returns:
            cont: 샘플링된 연속 행동. shape [B, cont_dim]. 범위 [-1, 1].
            disc_list: 브랜치별 이산 행동 텐서 리스트. 각 원소 shape [B].
            log_prob: 전체 행동의 결합 로그 확률. shape [B].
            value: 상태 가치 추정값. shape [B].
        """
        h = self._encode(vec_obs, point_cloud)

        # 연속 행동 — tanh-squashed Gaussian (행동 범위 [-1,1] 보장 + 올바른 log_prob)
        mean = self.cont_mean(h)                 # raw 평균 (tanh 는 샘플에 적용)
        std  = self.log_std.exp().expand_as(mean)
        dist = Normal(mean, std)
        u    = dist.rsample()                     # 원시 가우시안 샘플
        cont = torch.tanh(u)                      # [-1, 1] 로 squash
        # tanh 변환에 대한 log-det-Jacobian 보정 항
        log_prob = dist.log_prob(u).sum(-1) - torch.log(1.0 - cont.pow(2) + 1e-6).sum(-1)  # [B]

        # 이산 행동
        disc_list = []
        for head in self.disc_heads:
            d     = Categorical(logits=head(h))
            a     = d.sample()
            log_prob = log_prob + d.log_prob(a)
            disc_list.append(a)

        value = self.value_head(h).squeeze(-1)  # [B]
        return cont, disc_list, log_prob, value

    def evaluate(
        self,
        vec_obs: torch.Tensor,
        point_cloud: torch.Tensor,
        cont_actions: torch.Tensor,
        disc_actions: torch.Tensor
    ):
        """
        Args:
            vec_obs: 벡터 관측. shape [B, vec_dim].
            point_cloud: 모기 포인트 집합. shape [B, N, in_dim].
            cont_actions: 버퍼에서 꺼낸 연속 행동. shape [B, cont_dim].
            disc_actions: 버퍼에서 꺼낸 이산 행동. shape [B, len(disc_sizes)].
        Returns:
            log_prob: 현재 정책 기준 결합 로그 확률. shape [B].
            entropy: 현재 정책의 엔트로피 (탐색 장려 항). shape [B].
            value: 상태 가치 추정값. shape [B].
        """
        h = self._encode(vec_obs, point_cloud)

        # 연속 행동 log_prob + entropy (tanh-squashed Gaussian, get_action 과 동일 정의)
        mean = self.cont_mean(h)
        std  = self.log_std.exp().expand_as(mean)
        dist = Normal(mean, std)
        # 버퍼의 행동은 squash 된 값([-1,1]) → atanh 로 원시 u 복원 (수치 안정 위해 clamp)
        cont_clamped = cont_actions.clamp(-1.0 + 1e-6, 1.0 - 1e-6)
        u = torch.atanh(cont_clamped)
        log_prob = dist.log_prob(u).sum(-1) - torch.log(1.0 - cont_clamped.pow(2) + 1e-6).sum(-1)  # [B]
        entropy  = dist.entropy().sum(-1)               # [B] (squash 후 entropy 는 intractable → base Gaussian 근사)

        # 이산 행동 log_prob + entropy
        for i, head in enumerate(self.disc_heads):
            d = Categorical(logits=head(h))
            log_prob = log_prob + d.log_prob(disc_actions[:, i])
            entropy  = entropy  + d.entropy()

        value = self.value_head(h).squeeze(-1)  # [B]
        return log_prob, entropy, value

    def get_value(self, vec_obs: torch.Tensor, point_cloud: torch.Tensor) -> torch.Tensor:
        """
        상태 가치 V(s) 만 계산. truncation(시간초과) 종료 시 terminal obs 의 V 로
        GAE bootstrap 하기 위해 사용 (docs/RL_Design.md §3.4).
        Returns:
            value: shape [B].
        """
        h = self._encode(vec_obs, point_cloud)
        return self.value_head(h).squeeze(-1)  # [B]
