import torch
import torch.nn as nn
from pathlib import Path

from .communicator import UnityCommunicator
from .buffer import RolloutBuffer
from .ppo import PPO
from .curriculum import CurriculumManager
from .logger import MLflowLogger


class Trainer:
    def __init__(
        self,
        communicator: UnityCommunicator,
        model: nn.Module,
        ppo: PPO,
        buffer: RolloutBuffer,
        curriculum: CurriculumManager,
        logger: MLflowLogger,
        save_dir: str,
        max_iterations: int,
        log_interval: int = 10,
        save_interval: int = 200,
    ):
        self.communicator = communicator
        self.model = model
        self.ppo = ppo
        self.buffer = buffer
        self.curriculum = curriculum
        self.logger = logger
        self.save_dir = Path(save_dir)
        self.save_dir.mkdir(parents=True, exist_ok=True)
        self.max_iterations = max_iterations
        self.log_interval = log_interval
        self.save_interval = save_interval

    def train(self):
        print(f"[curriculum] start stage: {self.curriculum.stage_name}")
        total_steps = 0

        for iteration in range(self.max_iterations):
            self.buffer.reset()
            stage_idx = self.curriculum.stage_index
            last_vals, ep_rewards, ep_successes, ep_lengths, ep_timeouts = \
                self.communicator.collect(self.model, self.buffer)
            batch = self.buffer.get(last_vals)
            fire_attempt_rate = self.buffer.discrete_actions[:self.buffer.pointer].float().mean().item()
            result = self.ppo.update(batch)
            total_steps += self.buffer.pointer

            if self.curriculum.report(ep_successes):
                print(f"[curriculum] advance → {self.curriculum.stage_name} "
                      f"(success_rate={self.curriculum.last_advance_rate:.2f})")

            mean_reward = sum(ep_rewards) / len(ep_rewards) if ep_rewards else float("nan")
            mean_len = sum(ep_lengths) / len(ep_lengths) if ep_lengths else float("nan")
            timeout_rate = sum(ep_timeouts) / len(ep_timeouts) if ep_timeouts else float("nan")
            iter_succ = sum(ep_successes) / len(ep_successes) if ep_successes else float("nan")
            self.logger.log_metrics({
                "policy_loss": result.policy_loss,
                "value_loss": result.value_loss,
                "entropy_continuous": result.entropy_continuous,
                "entropy_discrete": result.entropy_discrete,  # 발사 탐색 붕괴 감시 — 0.1 미만이면 굳은 것
                "fire_attempt_rate": fire_attempt_rate,  # 난사 판별 — 1.0 근처면 매 스텝 발사 시도
                "approx_kl": result.approx_kl,
                "clip_fraction": result.clip_fraction,
                "explained_variance": result.explained_variance,
                "ep_reward_mean": mean_reward,
                "ep_len_mean": mean_len,
                "timeout_rate": timeout_rate,
                "success_rate": self.curriculum.success_rate,
                "stage": self.curriculum.stage_index + 1,
                f"by_stage/s{stage_idx+1}_success": iter_succ,
                f"by_stage/s{stage_idx+1}_reward": mean_reward,
                f"by_stage/s{stage_idx+1}_ep_len": mean_len,
            }, step=total_steps)

            if (iteration + 1) % self.log_interval == 0:
                print(f"[{iteration+1:5d}] stage={self.curriculum.stage_index+1} steps={total_steps:7d} | "
                      f"ep_reward={mean_reward:.2f} | succ={self.curriculum.success_rate:.2f} | "
                      f"len={mean_len:.0f} timeout={timeout_rate:.2f} | "
                      f"policy={result.policy_loss:.4f} value={result.value_loss:.4f} "
                      f"ent_c={result.entropy_continuous:.4f} ent_d={result.entropy_discrete:.4f} "
                      f"fire={fire_attempt_rate:.2f} | "
                      f"kl={result.approx_kl:.4f} clip={result.clip_fraction:.2f} ev={result.explained_variance:.2f}")

            if (iteration + 1) % self.save_interval == 0:
                self.save(f"model_{iteration+1}")

        self.save("model_final")
        self.logger.close()

    def save(self, tag: str):
        pt_path = self.save_dir / f"{tag}.pt"
        torch.save({"model": self.model.state_dict()}, pt_path)
        print(f"  saved → {pt_path}")
        self.logger.log_artifact(str(pt_path))
