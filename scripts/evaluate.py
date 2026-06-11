"""학습된 정책 평가 전용 진입점.

학습 없이 정책만 실행해 에피소드별 포획률·전멸률·타임아웃률·파손률을 집계한다.
기본은 결정론 모드(연속=분포 평균, 발사=최대 확률) — 탐색 노이즈 없는 실사용 성능 측정.

사용:
    python scripts/evaluate.py resume_path=results/run6/model_900.pt eval_episodes=50 eval_stage=6
"""
import sys
from pathlib import Path

import hydra
import torch
from omegaconf import DictConfig
from mlagents_envs.environment import UnityEnvironment
from mlagents_envs.base_env import ActionTuple
from mlagents_envs.side_channel.engine_configuration_channel import EngineConfigurationChannel
from mlagents_envs.side_channel.environment_parameters_channel import EnvironmentParametersChannel

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.network import ActorCritic
from src.utils import maybe_resume
from src.curriculum import CurriculumManager, STAGES
from src.communicator import REMAINING_OBS_INDEX, REMAINING_OBS_SCALE

# ChameleonAgent.CollectObservations 의 "혀 준비 상태" 위치 (벡터 관측 7번)
TONGUE_READY_OBS_INDEX = 7


def split_observations(observation_list, device):
    vector_numpy = next(o for o in observation_list if o.ndim == 2)
    point_cloud_candidates = [o for o in observation_list if o.ndim == 3]

    vector_tensor = torch.tensor(vector_numpy, dtype=torch.float32, device=device)
    if point_cloud_candidates:
        point_cloud_tensor = torch.tensor(point_cloud_candidates[0], dtype=torch.float32, device=device)
    else:
        point_cloud_tensor = torch.zeros(vector_tensor.shape[0], 0, 6, device=device)

    return vector_tensor, point_cloud_tensor


def read_remaining(observation_list):
    vector = next(o for o in observation_list if o.ndim == 1)
    return int(round(float(vector[REMAINING_OBS_INDEX]) * REMAINING_OBS_SCALE))


@hydra.main(version_base=None, config_path="../config", config_name="default")
def main(cfg: DictConfig):
    if not cfg.get("resume_path"):
        raise ValueError("resume_path 필요 — 예: resume_path=results/run6/model_900.pt")

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print("device =", device)

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

    stage_index = int(cfg.get("eval_stage", len(STAGES))) - 1
    curriculum = CurriculumManager(param_channel, STAGES, start_index=stage_index)
    curriculum.start()
    print(f"[evaluate] stage: {curriculum.stage_name}")

    env.reset()
    behavior_name = list(env.behavior_specs.keys())[0]
    spec = env.behavior_specs[behavior_name]
    vec_spec = next(s for s in spec.observation_specs if len(s.shape) == 1)
    observation_dim = vec_spec.shape[0]
    continuous_dim = spec.action_spec.continuous_size
    discrete_sizes = list(spec.action_spec.discrete_branches)

    model = ActorCritic(
        observation_dim=observation_dim, pointnet_out_dim=cfg["pointnet_out"],
        continuous_dim=continuous_dim, discrete_sizes=discrete_sizes,
    ).to(device)
    maybe_resume(model, cfg["resume_path"], device)
    model.eval()

    deterministic = bool(cfg.get("eval_deterministic", True))
    target_episodes = int(cfg.get("eval_episodes", 50))
    print(f"[evaluate] episodes={target_episodes} deterministic={deterministic}")

    spawn_by_agent: dict[int, int] = {}
    reward_by_agent: dict[int, float] = {}
    length_by_agent: dict[int, int] = {}
    shots_by_agent: dict[int, int] = {}
    results: list[dict] = []

    try:
        while len(results) < target_episodes:
            decision_steps, terminal_steps = env.get_steps(behavior_name)

            for agent_id in terminal_steps.agent_id:
                aid = int(agent_id)
                spawn_count = spawn_by_agent.pop(aid, None)
                if spawn_count is None:
                    continue
                terminal = terminal_steps[agent_id]
                total_reward = reward_by_agent.pop(aid, 0.0) + float(terminal.reward)
                remaining = read_remaining(terminal.obs)
                caught = max(0, spawn_count - remaining)
                if bool(terminal.interrupted):
                    outcome = "timeout"
                elif remaining == 0:
                    outcome = "clear"
                else:
                    outcome = "break"
                results.append({
                    "spawn": spawn_count,
                    "caught": caught,
                    "catch_rate": caught / spawn_count if spawn_count > 0 else 0.0,
                    "outcome": outcome,
                    "reward": total_reward,
                    "length": length_by_agent.pop(aid, 0) + 1,
                    "shots": shots_by_agent.pop(aid, 0),
                })
                if len(results) % 10 == 0:
                    print(f"  [{len(results):3d}/{target_episodes}] 최근: {results[-1]['caught']}/{results[-1]['spawn']} 포획, {results[-1]['outcome']}")
                if len(results) >= target_episodes:
                    break
            if len(results) >= target_episodes:
                break

            if len(decision_steps) > 0:
                observation_vector, point_cloud = split_observations(decision_steps.obs, device)
                with torch.no_grad():
                    if deterministic:
                        continuous_actions, discrete_actions = model.get_deterministic_action(observation_vector, point_cloud)
                    else:
                        continuous_actions, _, discrete_actions, _, _ = model.get_action(observation_vector, point_cloud)

                for i, agent_id in enumerate(decision_steps.agent_id):
                    aid = int(agent_id)
                    if aid not in spawn_by_agent:
                        spawn_by_agent[aid] = int(round(
                            observation_vector[i, REMAINING_OBS_INDEX].item() * REMAINING_OBS_SCALE))
                    reward_by_agent[aid] = reward_by_agent.get(aid, 0.0) + float(decision_steps[agent_id].reward)
                    length_by_agent[aid] = length_by_agent.get(aid, 0) + 1
                    tongue_ready = observation_vector[i, TONGUE_READY_OBS_INDEX].item() > 0.5
                    if tongue_ready and int(discrete_actions[i, 0].item()) == 1:
                        shots_by_agent[aid] = shots_by_agent.get(aid, 0) + 1

                env.set_actions(behavior_name, ActionTuple(
                    continuous=continuous_actions.cpu().numpy(),
                    discrete=discrete_actions.cpu().numpy().astype("int32"),
                ))

            env.step()
    finally:
        env.close()

    episode_count = len(results)
    total_spawn = sum(r["spawn"] for r in results)
    total_caught = sum(r["caught"] for r in results)
    total_shots = sum(r["shots"] for r in results)
    clear_count = sum(1 for r in results if r["outcome"] == "clear")
    timeout_count = sum(1 for r in results if r["outcome"] == "timeout")
    break_count = sum(1 for r in results if r["outcome"] == "break")
    mean_catch_rate = sum(r["catch_rate"] for r in results) / episode_count
    mean_reward = sum(r["reward"] for r in results) / episode_count
    mean_length = sum(r["length"] for r in results) / episode_count
    mean_shots = total_shots / episode_count
    accuracy = total_caught / total_shots if total_shots > 0 else float("nan")

    print()
    print(f"=== 평가 결과: {cfg['resume_path']} | {curriculum.stage_name} | {episode_count} 에피소드 ===")
    print(f"  포획률 (평균)        : {mean_catch_rate:.2f}  ({total_caught}/{total_spawn} 마리)")
    print(f"  전멸률 (모두 포획)    : {clear_count / episode_count:.2f}  ({clear_count}회)")
    print(f"  타임아웃률           : {timeout_count / episode_count:.2f}  ({timeout_count}회)")
    print(f"  가구 파손률          : {break_count / episode_count:.2f}  ({break_count}회)")
    print(f"  에피소드당 발사       : {mean_shots:.1f}발 | 발당 명중률: {accuracy:.2f}")
    print(f"  평균 보상 / 길이      : {mean_reward:.2f} / {mean_length:.0f} 스텝")


if __name__ == "__main__":
    main()
