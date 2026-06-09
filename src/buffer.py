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
        gamma: float, # discount factor
        lamda: float, # lambda
        device: torch.device
    ):
        self.buffer_size = buffer_size
        self.gamma = gamma
        self.lamda = lamda
        self.device = device

        self.observation_vector = torch.zeros(buffer_size, observation_dim)
        self.continuous_actions = torch.zeros(buffer_size, continuous_dim)
        self.discrete_actions = torch.zeros(buffer_size, discrete_size, dtype=torch.long)

        self.log_probs = torch.zeros(buffer_size)
        self.rewards = torch.zeros(buffer_size)
        self.values = torch.zeros(buffer_size)
        self.dones = torch.zeros(buffer_size)
        self.bootstraps = torch.zeros(buffer_size)
        
        self.pointer = 0
        self.point_clouds = []

    def add(
        self,
        observation_vector: torch.Tensor,
        point_cloud: torch.Tensor,
        continuous_action: torch.Tensor,
        discrete_action: torch.Tensor,
        log_prob: torch.Tensor,
        reward: float,
        value: torch.Tensor,
        done: bool,
        bootstrap_value: float = 0.0,
    ):
        i = self.pointer
        
        # 지정된 pointer 위치에 데이터들을 CPU로 저장
        self.observation_vector[i] = observation_vector.cpu()
        self.point_clouds.append(point_cloud.cpu())
        self.continuous_actions[i] = continuous_action.cpu()
        self.discrete_actions[i] = discrete_action.cpu()
        self.log_probs[i] = log_prob.cpu()
        self.rewards[i] = reward
        self.values[i] = value.cpu()
        self.dones[i] = float(done) 
        self.bootstraps[i] = bootstrap_value
        
        self.pointer += 1

    def compute_gae(self, last_value: float):
        advantages = torch.zeros(self.pointer)
        last_gae = 0.0

        for t in reversed(range(self.pointer)):
            done = self.dones[t].item()

            if done:
                next_value = self.bootstraps[t].item()
            elif t == self.pointer - 1:
                next_value = last_value
            else:
                next_value = self.values[t+1].item()
            
            # TD Error
            delta = self.rewards[t] + self.gamma * next_value - self.values[t]
            # GAE 누적 및 전파
            last_gae = delta + self.gamma * self.lamda * (1.0 - done) * last_gae
            advantages[t] = last_gae
        
        target_values = advantages + self.values[:self.pointer]
        return advantages, target_values
    
    def get(self, last_value: float):
        advantages, target_values = self.compute_gae(last_value)
        # Normalization
        advantages = (advantages - advantages.mean()) / (advantages.std() + 1e-8)
        point_clouds = collate_point_cloud(self.point_clouds[:self.pointer], self.device)
        return RolloutBatch(
            observation_vector=self.observation_vector[:self.pointer].to(self.device),
            point_clouds=point_clouds,
            continuous_actions=self.continuous_actions[:self.pointer].to(self.device),
            discrete_actions=self.discrete_actions[:self.pointer].to(self.device),
            log_probs=self.log_probs[:self.pointer].to(self.device),
            advantages=advantages.to(self.device),
            target_values=target_values.to(self.device),
        )
    def reset(self):
        self.pointer = 0
        self.point_clouds.clear()
