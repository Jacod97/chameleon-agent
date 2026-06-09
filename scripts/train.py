import sys
from pathlib import Path

import hydra
import torch
from omegaconf import DictConfig
from mlagents_envs.environment import UnityEnvironment
from mlagents_envs.side_channel.engine_configuration_channel import EngineConfigurationChannel
from mlagents_envs.side_channel.environment_parameters_channel import EnvironmentParametersChannel

# 프로젝트 루트를 path 에 추가 → refactoring 패키지 import 가능
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from refactoring.network import ActorCritic
from refactoring.buffer import RolloutBuffer
from refactoring.ppo import PPO
from refactoring.communicator import UnityCommunicator
from refactoring.curriculum import CurriculumManager, STAGES
from refactoring.logger import MLflowLogger
from refactoring.trainer import Trainer


@hydra.main(version_base=None, config_path="../config", config_name="default")
def main(cfg: DictConfig):
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print("device =", device)

    # --- 환경 + 사이드 채널 ---
    engine_channel = EngineConfigurationChannel()
    param_channel = EnvironmentParametersChannel()
    env = UnityEnvironment(
        file_name=cfg.get("env_path"),
        seed=cfg.get("seed", 0),
        timeout_wait=120,
        no_graphics=cfg.get("no_graphics", False),
        side_channels=[engine_channel, param_channel],
    )
    engine_channel.set_configuration_parameters(time_scale=float(cfg.get("time_scale", 20.0)))

    # --- 커리큘럼: 1단계 파라미터를 env.reset 전에 주입 ---
    curriculum = CurriculumManager(
        param_channel, STAGES,
        threshold=cfg.get("curriculum_threshold", 0.8),
        window=cfg.get("curriculum_window", 50),
    )
    curriculum.start()

    env.reset()
    behavior_name = list(env.behavior_specs.keys())[0]
    spec = env.behavior_specs[behavior_name]
    vec_spec = next(s for s in spec.observation_specs if len(s.shape) == 1)
    observation_dim = vec_spec.shape[0]
    continuous_dim = spec.action_spec.continuous_size
    discrete_sizes = list(spec.action_spec.discrete_branches)
    print(f"behavior={behavior_name} | obs={observation_dim} cont={continuous_dim} disc={discrete_sizes}")

    # --- 모듈 조립 (값 주입) ---
    model = ActorCritic(
        observation_dim=observation_dim, pointnet_out_dim=cfg["pointnet_out"],
        continuous_dim=continuous_dim, discrete_sizes=discrete_sizes,
    ).to(device)
    ppo = PPO(
        model=model, lr=cfg["lr"], clip_epsilon=cfg["clip_eps"],
        value_loss_weight=cfg["vf_coef"], entropy_loss_weight=cfg["ent_coef"],
        gradient_clip_max=cfg["max_grad_norm"], epochs=cfg["n_epochs"], batch_size=cfg["batch_size"],
    )
    buffer = RolloutBuffer(
        buffer_size=cfg["buf_size"], observation_dim=observation_dim,
        continuous_dim=continuous_dim, discrete_size=len(discrete_sizes),
        gamma=cfg["gamma"], lamda=cfg["lam"], device=device,
    )
    communicator = UnityCommunicator(env, behavior_name, device)

    logger = MLflowLogger(experiment_name="chameleon-rl")
    logger.log_params({
        "lr": cfg["lr"], "clip_eps": cfg["clip_eps"], "vf_coef": cfg["vf_coef"],
        "ent_coef": cfg["ent_coef"], "max_grad_norm": cfg["max_grad_norm"],
        "n_epochs": cfg["n_epochs"], "batch_size": cfg["batch_size"], "buf_size": cfg["buf_size"],
        "gamma": cfg["gamma"], "lam": cfg["lam"], "time_scale": cfg.get("time_scale", 20.0),
        "pointnet_out": cfg["pointnet_out"], "seed": cfg.get("seed", 0),
        "curriculum_threshold": cfg.get("curriculum_threshold", 0.8),
        "curriculum_window": cfg.get("curriculum_window", 50),
    })

    trainer = Trainer(
        communicator=communicator, model=model, ppo=ppo, buffer=buffer,
        curriculum=curriculum, logger=logger, save_dir=cfg["save_dir"],
        max_iterations=cfg["max_iterations"], log_interval=cfg["log_interval"],
        save_interval=cfg["save_interval"],
    )

    try:
        trainer.train()
    finally:
        env.close()


if __name__ == "__main__":
    main()
