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
            last_vals, ep_rewards, ep_successes = self.communicator.collect(self.model, self.buffer)
            batch = self.buffer.get(last_vals)
            result = self.ppo.update(batch)
            total_steps += self.buffer.pointer

            if self.curriculum.report(ep_successes):
                print(f"[curriculum] advance → {self.curriculum.stage_name} "
                      f"(success_rate={self.curriculum.success_rate:.2f})")

            mean_reward = sum(ep_rewards) / len(ep_rewards) if ep_rewards else float("nan")
            self.logger.log_metrics({
                "policy_loss": result.policy_loss,
                "value_loss": result.value_loss,
                "entropy_continuous": result.entropy_continuous,
                "entropy_discrete": result.entropy_discrete,  # 발사 탐색 붕괴 감시 — 0.1 미만이면 굳은 것
                "ep_reward_mean": mean_reward,
                "success_rate": self.curriculum.success_rate,
                "stage": self.curriculum.stage_index + 1,
            }, step=total_steps)

            if (iteration + 1) % self.log_interval == 0:
                print(f"[{iteration+1:5d}] stage={self.curriculum.stage_index+1} steps={total_steps:7d} | "
                      f"ep_reward={mean_reward:.2f} | succ={self.curriculum.success_rate:.2f} | "
                      f"policy={result.policy_loss:.4f} value={result.value_loss:.4f} "
                      f"ent_c={result.entropy_continuous:.4f} ent_d={result.entropy_discrete:.4f}")

            if (iteration + 1) % self.save_interval == 0:
                self.save(f"model_{iteration+1}")

        self.save("model_final")
        self.logger.close()

    def save(self, tag: str):
        pt_path = self.save_dir / f"{tag}.pt"
        torch.save({"model": self.model.state_dict()}, pt_path)
        print(f"  saved → {pt_path}")
        self.logger.log_artifact(str(pt_path))
