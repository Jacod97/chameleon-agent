import torch
import torch.nn as nn

from ._type import RolloutBatch, PPOResult

class PPO:
    def __init__(
        self,
        model: nn.Module,
        lr: float,
        clip_epsilon: float,
        value_loss_weight: float,
        entropy_loss_weight: float,
        discrete_entropy_weight: float,
        gradient_clip_max: float,
        epochs: int,
        batch_size: int
    ):
        self.model = model
        self.clip_epsilon = clip_epsilon
        self.value_loss_weight = value_loss_weight
        self.entropy_loss_weight = entropy_loss_weight
        self.discrete_entropy_weight = discrete_entropy_weight
        self.gradient_clip_max = gradient_clip_max
        self.epochs = epochs
        self.batch_size = batch_size

        self.optimizer = torch.optim.Adam(model.parameters(), lr=lr)

    def update(self, batch: RolloutBatch):

        observation_vector = batch.observation_vector
        point_clouds = batch.point_clouds
        pre_tanh_actions = batch.pre_tanh_actions
        discrete_actions = batch.discrete_actions
        old_log_probs = batch.log_probs
        advantages = batch.advantages
        target_values = batch.target_values

        buffer_data_num = observation_vector.shape[0]
        index = torch.arange(buffer_data_num, device=observation_vector.device)
        accumulated_result = PPOResult()

        for _ in range(self.epochs):
            perm = index[torch.randperm(buffer_data_num)] # data random sampling

            for start in range(0, buffer_data_num, self.batch_size):
                mini_batch = perm[start: start + self.batch_size]

                log_prob, entropy_cont, entropy_disc, value = self.model.evaluate(
                    observation_vector[mini_batch],
                    point_clouds[mini_batch],
                    pre_tanh_actions[mini_batch],
                    discrete_actions[mini_batch]
                )

                log_ratio = log_prob - old_log_probs[mini_batch]
                ratio = log_ratio.exp()
                advantage = advantages[mini_batch]

                unclipped_surrogate = ratio * advantage
                clipped_surrogate = ratio.clamp(1.0 - self.clip_epsilon, 1.0 + self.clip_epsilon) * advantage

                policy_loss = -torch.min(unclipped_surrogate, clipped_surrogate).mean()
                value_loss = (target_values[mini_batch] - value).pow(2).mean() # Critic 손실 (정답 target_value와의 MSE 차이)
                entropy_loss = -(self.entropy_loss_weight * entropy_cont.mean()
                                 + self.discrete_entropy_weight * entropy_disc.mean())

                loss = policy_loss + self.value_loss_weight * value_loss + entropy_loss

                self.optimizer.zero_grad()
                loss.backward()
                nn.utils.clip_grad_norm_(self.model.parameters(), self.gradient_clip_max)
                self.optimizer.step()

                accumulated_result.policy_loss += policy_loss.item()
                accumulated_result.value_loss += value_loss.item()
                accumulated_result.entropy_continuous += entropy_cont.mean().item()
                accumulated_result.entropy_discrete += entropy_disc.mean().item()

                with torch.no_grad():
                    minibatch_target_values = target_values[mini_batch]
                    accumulated_result.approx_kl += ((ratio - 1.0) - log_ratio).mean().item()
                    accumulated_result.clip_fraction += ((ratio - 1.0).abs() > self.clip_epsilon).float().mean().item()
                    accumulated_result.explained_variance += (
                        1.0 - (minibatch_target_values - value).var() / (minibatch_target_values.var() + 1e-8)
                    ).item()

        n_minibatches = (buffer_data_num + self.batch_size - 1) // self.batch_size
        steps = self.epochs * max(1, n_minibatches)
        return accumulated_result.averaged(steps)
