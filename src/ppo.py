import torch
import torch.nn as nn
from torch.utils.data import DataLoader, TensorDataset

from ._type import RolloutBatch, PPOResult

class PPO:
    def __init__(
        self,
        model: nn.Module,
        lr: float,
        clip_epsilon: float,
        value_loss_weight: float,
        entropy_loss_weight: float,
        gradient_clip_max: float,
        epochs: int,
        batch_size: int
    ):
        self.model = model
        self.clip_epsilon = clip_epsilon
        self.value_loss_weight = value_loss_weight
        self.entropy_loss_weight = entropy_loss_weight
        self.gradient_clip_max = gradient_clip_max
        self.epochs = epochs
        self.batch_size = batch_size

        self.optimizer = torch.optim.Adam(model.parameters(), lr=lr)

    def update(self, batch: RolloutBatch):

        observation_vector = batch.observation_vector
        point_clouds = batch.point_clouds
        continuous_actions = batch.continuous_actions
        discrete_actions = batch.discrete_actions
        old_log_probs = batch.log_probs
        advantages = batch.advantages
        target_values = batch.target_values

        buffer_data_num = observation_vector.shape[0]
        index = torch.arange(buffer_data_num, device=observation_vector.device)
        total_loss_dict = {
            "policy" : 0.0,
            "value": 0.0,
            "entropy": 0.0
        }

        for _ in range(self.epochs):
            perm = index[torch.randperm(buffer_data_num)] # data random sampling

            for start in range(0, buffer_data_num, self.batch_size):
                mini_batch = perm[start: start + self.batch_size]

                log_prob, entropy, value = self.model.evaluate(
                    observation_vector[mini_batch],
                    point_clouds[mini_batch],
                    continuous_actions[mini_batch],
                    discrete_actions[mini_batch]
                )

                ratio = (log_prob - old_log_probs[mini_batch]).exp()
                advantage = advantages[mini_batch]

                unclipped_surrogate = ratio * advantage
                clipped_surrogate = ratio.clamp(1.0 - self.clip_epsilon, 1.0 + self.clip_epsilon) * advantage

                policy_loss = -torch.min(unclipped_surrogate, clipped_surrogate).mean()
                value_loss = (target_values[mini_batch] - value).pow(2).mean() # Critic 손실 (정답 target_value와의 MSE 차이)
                entropy_loss = -entropy.mean()

                loss = policy_loss + self.value_loss_weight * value_loss + self.entropy_loss_weight * entropy_loss

                self.optimizer.zero_grad()
                loss.backward()
                nn.utils.clip_grad_norm_(self.model.parameters(), self.gradient_clip_max)
                self.optimizer.step()

                total_loss_dict["policy"] += policy_loss.item()
                total_loss_dict["value"] += value_loss.item()
                total_loss_dict["entropy"] += entropy.mean().item()

        n_minibatches = (buffer_data_num + self.batch_size - 1) // self.batch_size
        steps = self.epochs * max(1, n_minibatches)

        return PPOResult(
            policy_loss= total_loss_dict["policy"] / steps,
            value_loss= total_loss_dict["value"] / steps,
            entropy= total_loss_dict["entropy"] / steps
        )