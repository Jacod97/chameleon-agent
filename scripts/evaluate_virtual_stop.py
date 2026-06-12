"""구(舊) 규칙 빌드에서 학습한 정책을 "배포용 무감지 정지 규칙"으로 평가하는 진입점.

구 빌드(전지적 전멸 종료, 관측 10차원)를 그대로 실행하되, Python 측에서
"모기 무감지 N초 지속 → 그 시점에 로봇이 정지했다고 가정"하는 가상 정지를 판정해
그 순간의 포획 수·전멸 여부를 배포 성능으로 집계한다.
구 정책(예: run6)과 신 종료 규칙으로 학습한 정책을 같은 잣대로 비교하는 용도.

사용:
    python scripts/evaluate_virtual_stop.py env_path=Builds_eval/MainEnv/Chameleon_env.exe \
        resume_path=results/run6/model_900.pt eval_stage=7 eval_episodes=50
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

# 결정 스텝 간격(초) = Time.fixedDeltaTime(0.02) × DecisionPeriod(5)
DECISION_INTERVAL_SECONDS = 0.1


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

    virtual_stop_seconds = float(cfg.get("virtual_stop_seconds", 25.0))
    virtual_stop_decisions = int(round(virtual_stop_seconds / DECISION_INTERVAL_SECONDS))
    target_episodes = int(cfg.get("eval_episodes", 50))
    print(f"[virtual-stop] stage: {curriculum.stage_name} | episodes={target_episodes} | "
          f"무감지 {virtual_stop_seconds}s ({virtual_stop_decisions} decisions)")

    env.reset()
    behavior_name = list(env.behavior_specs.keys())[0]
    spec = env.behavior_specs[behavior_name]
    vec_spec = next(s for s in spec.observation_specs if len(s.shape) == 1)
    observation_dim = vec_spec.shape[0]
    continuous_dim = spec.action_spec.continuous_size
    discrete_sizes = list(spec.action_spec.discrete_branches)
    print(f"behavior obs={observation_dim} (구 빌드면 10이어야 함)")

    model = ActorCritic(
        observation_dim=observation_dim, pointnet_out_dim=cfg["pointnet_out"],
        continuous_dim=continuous_dim, discrete_sizes=discrete_sizes,
    ).to(device)
    maybe_resume(model, cfg["resume_path"], device)
    model.eval()

    spawn_by_agent: dict[int, int] = {}
    streak_by_agent: dict[int, int] = {}
    length_by_agent: dict[int, int] = {}
    virtual_by_agent: dict[int, dict] = {}
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
                remaining = read_remaining(terminal.obs)
                interrupted = bool(terminal.interrupted)
                virtual = virtual_by_agent.pop(aid, None)

                if virtual is None:
                    if not interrupted and remaining == 0:
                        # 전멸 종료 — 배포 로봇이라면 25s 대기 후 정지했을 것 → 가상 전멸 성공
                        virtual = {"caught": spawn_count, "clear": True,
                                   "length": length_by_agent.get(aid, 0), "fired": True}
                    else:
                        # MaxStep 까지 가상 정지 미발동 — 배포라면 계속 가동 중이었을 상황
                        virtual = {"caught": max(0, spawn_count - remaining), "clear": False,
                                   "length": length_by_agent.get(aid, 0), "fired": False}

                results.append({
                    "spawn": spawn_count,
                    "virtual_caught": virtual["caught"],
                    "virtual_clear": virtual["clear"],
                    "virtual_fired": virtual["fired"],
                    "virtual_length": virtual["length"],
                    "real_caught": max(0, spawn_count - remaining),
                    "real_timeout": interrupted,
                })
                streak_by_agent.pop(aid, None)
                length_by_agent.pop(aid, None)
                if len(results) % 10 == 0:
                    print(f"  [{len(results):3d}/{target_episodes}]")
                if len(results) >= target_episodes:
                    break
            if len(results) >= target_episodes:
                break

            if len(decision_steps) > 0:
                observation_vector, point_cloud = split_observations(decision_steps.obs, device)
                with torch.no_grad():
                    continuous_actions, discrete_actions = model.get_deterministic_action(observation_vector, point_cloud)

                detected_counts = (point_cloud.abs().sum(dim=-1) > 0).sum(dim=1)

                for i, agent_id in enumerate(decision_steps.agent_id):
                    aid = int(agent_id)
                    if aid not in spawn_by_agent:
                        spawn_by_agent[aid] = int(round(
                            observation_vector[i, REMAINING_OBS_INDEX].item() * REMAINING_OBS_SCALE))
                        streak_by_agent[aid] = 0
                        length_by_agent[aid] = 0
                    length_by_agent[aid] = length_by_agent.get(aid, 0) + 1

                    if aid not in virtual_by_agent:
                        if int(detected_counts[i].item()) > 0:
                            streak_by_agent[aid] = 0
                        else:
                            streak_by_agent[aid] = streak_by_agent.get(aid, 0) + 1
                        if streak_by_agent[aid] >= virtual_stop_decisions:
                            remaining_now = int(round(
                                observation_vector[i, REMAINING_OBS_INDEX].item() * REMAINING_OBS_SCALE))
                            virtual_by_agent[aid] = {
                                "caught": max(0, spawn_by_agent[aid] - remaining_now),
                                "clear": remaining_now == 0,
                                "length": length_by_agent[aid],
                                "fired": True,
                            }

                env.set_actions(behavior_name, ActionTuple(
                    continuous=continuous_actions.cpu().numpy(),
                    discrete=discrete_actions.cpu().numpy().astype("int32"),
                ))

            env.step()
    finally:
        env.close()

    episode_count = len(results)
    total_spawn = sum(r["spawn"] for r in results)
    virtual_caught = sum(r["virtual_caught"] for r in results)
    virtual_clear_count = sum(1 for r in results if r["virtual_clear"])
    virtual_fired_count = sum(1 for r in results if r["virtual_fired"])
    real_caught = sum(r["real_caught"] for r in results)
    real_timeout_count = sum(1 for r in results if r["real_timeout"])
    mean_virtual_length = sum(r["virtual_length"] for r in results) / episode_count

    print()
    print(f"=== 가상 정지 평가: {cfg['resume_path']} | {curriculum.stage_name} | {episode_count} 에피소드 ===")
    print(f"  [배포 규칙 기준: 무감지 {virtual_stop_seconds}s 정지]")
    print(f"  포획률              : {virtual_caught / total_spawn:.2f}  ({virtual_caught}/{total_spawn} 마리)")
    print(f"  전멸률              : {virtual_clear_count / episode_count:.2f}  ({virtual_clear_count}회)")
    print(f"  정지 발동률          : {virtual_fired_count / episode_count:.2f}  (미발동 = MaxStep 내 무감지 구간 없음)")
    print(f"  정지 시점 평균       : {mean_virtual_length:.0f} 결정 스텝")
    print(f"  [참고: 구 규칙 기준]")
    print(f"  포획률 / 타임아웃률  : {real_caught / total_spawn:.2f} / {real_timeout_count / episode_count:.2f}")


if __name__ == "__main__":
    main()
