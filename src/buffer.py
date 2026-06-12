import torch

from .utils import collate_point_cloud
from ._type import RolloutBatch

class RolloutBuffer:
    def __init__(
        self,
        buffer_size: int,
        observation_dim: int,
        continuous_dim: int,
        discrete_size: int,
        gamma: float,
        lamda: float,
        device: torch.device
    ):
        self.buffer_size = buffer_size
        self.gamma = gamma
        self.lamda = lamda
        self.device = device

        self.observation_vector = torch.zeros(buffer_size, observation_dim)
        self.pre_tanh_actions = torch.zeros(buffer_size, continuous_dim)
        self.discrete_actions = torch.zeros(buffer_size, discrete_size, dtype=torch.long)

        self.log_probs = torch.zeros(buffer_size)
        self.rewards = torch.zeros(buffer_size)
        self.values = torch.zeros(buffer_size)
        self.dones = torch.zeros(buffer_size)
        self.bootstraps = torch.zeros(buffer_size)
        self.agent_ids = torch.zeros(buffer_size, dtype=torch.long)

        self.pointer = 0
        self.point_clouds = []

    def add(
        self,
        observation_vector: torch.Tensor,
        point_cloud: torch.Tensor,
        pre_tanh_action: torch.Tensor,
        discrete_action: torch.Tensor,
        log_prob: torch.Tensor,
        reward: float,
        value: torch.Tensor,
        done: bool,
        agent_id: int,
        bootstrap_value: float = 0.0,
    ):
        i = self.pointer

        self.observation_vector[i] = observation_vector.cpu()
        self.point_clouds.append(point_cloud.cpu())
        self.pre_tanh_actions[i] = pre_tanh_action.cpu()
        self.discrete_actions[i] = discrete_action.cpu()
        self.log_probs[i] = log_prob.cpu()
        self.rewards[i] = reward
        self.values[i] = value.cpu()
        self.dones[i] = float(done)
        self.bootstraps[i] = bootstrap_value
        self.agent_ids[i] = agent_id

        self.pointer += 1

    def compute_gae(self, last_vals: dict):
        """에이전트별 독립 GAE 계산. 병렬 에이전트 간 크로스 오염 방지."""
        advantages = torch.zeros(self.pointer)

        # 에이전트 ID별 transition 인덱스 그룹화 (시간 순서 유지)
        agent_indices: dict[int, list[int]] = {}
        for t in range(self.pointer):
            aid = int(self.agent_ids[t].item())
            if aid not in agent_indices:
                agent_indices[aid] = []
            agent_indices[aid].append(t)

        for aid, indices in agent_indices.items():
            last_gae = 0.0
            for k in reversed(range(len(indices))):
                t = indices[k]
                done = self.dones[t].item()

                if done:
                    next_value = self.bootstraps[t].item()
                    last_gae = 0.0
                elif k == len(indices) - 1:
                    # 버퍼 내 마지막 transition: 수집 종료 시점의 value로 bootstrap
                    next_value = last_vals.get(aid, 0.0)
                else:
                    # 같은 에이전트의 다음 transition value (올바른 temporal credit)
                    next_value = self.values[indices[k + 1]].item()

                delta = self.rewards[t] + self.gamma * next_value - self.values[t]
                last_gae = delta + self.gamma * self.lamda * (1.0 - float(done)) * last_gae
                advantages[t] = last_gae

        target_values = advantages + self.values[:self.pointer]
        return advantages, target_values

    def get(self, last_vals: dict):
        advantages, target_values = self.compute_gae(last_vals)
        advantages = (advantages - advantages.mean()) / (advantages.std() + 1e-8)
        point_clouds = collate_point_cloud(self.point_clouds[:self.pointer], self.device)
        return RolloutBatch(
            observation_vector=self.observation_vector[:self.pointer].to(self.device),
            point_clouds=point_clouds,
            pre_tanh_actions=self.pre_tanh_actions[:self.pointer].to(self.device),
            discrete_actions=self.discrete_actions[:self.pointer].to(self.device),
            log_probs=self.log_probs[:self.pointer].to(self.device),
            advantages=advantages.to(self.device),
            target_values=target_values.to(self.device),
        )

    def reset(self):
        self.pointer = 0
        self.point_clouds.clear()
