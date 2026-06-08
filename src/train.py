import torch
from pathlib import Path
from omegaconf import DictConfig
from torch.utils.tensorboard import SummaryWriter
from mlagents_envs.environment import UnityEnvironment
from mlagents_envs.base_env import ActionTuple
from mlagents_envs.side_channel.engine_configuration_channel import EngineConfigurationChannel

from network import ActorCritic
from buffer import RolloutBuffer
from ppo import PPO


def _split_batched_obs(obs_list, device: torch.device):
    """
    decision_steps.obs (배치 포함) → (vec_t [B, vec_dim], pt_t [B, N, 6]).
    벡터는 rank-2, 모기 BufferSensor는 rank-3 로 구분.
    """
    vec_np   = next(o for o in obs_list if o.ndim == 2)
    pt_cands = [o for o in obs_list if o.ndim == 3]
    vec_t = torch.tensor(vec_np, dtype=torch.float32, device=device)
    if pt_cands:
        pt_t = torch.tensor(pt_cands[0], dtype=torch.float32, device=device)
    else:
        pt_t = torch.zeros(vec_t.shape[0], 0, 6, device=device)
    return vec_t, pt_t


def _terminal_value(model: ActorCritic, term_step, device: torch.device) -> float:
    """
    시간초과(truncated)된 에이전트의 terminal obs 에서 V(s_terminal) 계산.
    term_step.obs 는 배치 차원이 없음: 벡터 rank-1, 모기 rank-2.
    """
    obs = term_step.obs
    vec_np   = next(o for o in obs if o.ndim == 1)
    pt_cands = [o for o in obs if o.ndim == 2]
    vec_t = torch.tensor(vec_np[None], dtype=torch.float32, device=device)
    if pt_cands:
        pt_t = torch.tensor(pt_cands[0][None], dtype=torch.float32, device=device)
    else:
        pt_t = torch.zeros(1, 0, 6, device=device)
    with torch.no_grad():
        return model.get_value(vec_t, pt_t)[0].item()


def collect_rollout(
    env: UnityEnvironment,
    model: ActorCritic,
    buf: RolloutBuffer,
    device: torch.device,
    behavior_name: str,
):
    """
    Args:
        env: Unity 환경.
        model: ActorCritic 네트워크.
        buf: 비어있는 RolloutBuffer.
        device: 디바이스.
        behavior_name: ML-Agents behavior 이름.
    Returns:
        last_value: 버퍼 마지막 상태(경계 아님)의 V(s). GAE 부트스트랩에 사용.
        ep_rewards: 에피소드별 누적 보상 리스트.

    보상 타이밍: 시점 t 에 정한 행동의 보상은 env.step() 이후의 get_steps()
    (next_dec / next_term) 에 도착하므로, 그 값을 해당 전이에 기록한다 (off-by-one 방지).
    종료 처리(docs/RL_Design.md §3.4): terminal_steps.interrupted 로 구분 —
    True=시간초과(truncated, V bootstrap), False=진짜 종료(성공/파손, bootstrap 0).
    """
    model.eval()
    ep_rewards = []
    ep_reward  = 0.0
    last_value = 0.0

    while buf.ptr < buf.buf_size:
        decision_steps, _ = env.get_steps(behavior_name)

        if len(decision_steps) == 0:
            # 이번 프레임 결정 대기 에이전트 없음 (전부 종료/리셋 중) — 진행만
            env.step()
            continue

        vec_t, pt_t = _split_batched_obs(decision_steps.obs, device)

        with torch.no_grad():
            cont, disc_list, log_prob, value = model.get_action(vec_t, pt_t)

        # ActionTuple 구성 (모든 이산 브랜치 포함)
        cont_np = cont.cpu().numpy()
        disc_np = torch.stack(disc_list, dim=-1).cpu().numpy().astype("int32")
        env.set_actions(behavior_name, ActionTuple(continuous=cont_np, discrete=disc_np))
        env.step()

        # 방금 취한 행동의 결과(보상·종료)는 다음 get_steps 에서 도착
        next_dec, next_term = env.get_steps(behavior_name)

        for i in range(len(decision_steps)):
            agent_id = decision_steps.agent_id[i]

            if agent_id in next_term:
                ts = next_term[agent_id]
                reward      = float(ts.reward)
                interrupted = bool(ts.interrupted)   # True = 시간초과(truncated)
                boundary    = True
                # truncated → terminal obs 의 V 로 bootstrap, 진짜 종료 → 0
                bootstrap_value = _terminal_value(model, ts, device) if interrupted else 0.0
            elif agent_id in next_dec:
                reward          = float(next_dec[agent_id].reward)
                boundary        = False
                bootstrap_value = 0.0
            else:
                # decision period>1 등으로 즉시 재등장하지 않은 경우 (현 설정에선 미발생)
                reward          = 0.0
                boundary        = False
                bootstrap_value = 0.0

            ep_reward += reward
            buf.add(
                vec_obs         = vec_t[i].cpu(),
                point_cloud     = pt_t[i].cpu(),
                cont_act        = cont[i].cpu(),
                disc_act        = torch.stack([d[i] for d in disc_list], dim=-1).cpu(),
                log_prob        = log_prob[i].cpu(),
                reward          = reward,
                value           = value[i].cpu(),
                done            = boundary,
                bootstrap_value = bootstrap_value,
            )

            if boundary:
                ep_rewards.append(ep_reward)
                ep_reward  = 0.0
                last_value = 0.0
            else:
                last_value = value[i].item()

            if buf.ptr >= buf.buf_size:
                break

    model.train()
    return last_value, ep_rewards


def train(cfg: DictConfig):
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    save_dir = Path(cfg["save_dir"])
    save_dir.mkdir(parents=True, exist_ok=True)
    writer = SummaryWriter(log_dir=str(save_dir / "tb"))

    # 엔진 설정 채널: 배속(time_scale)·렌더 해상도 등을 Python 에서 제어.
    # 빌드(standalone) 실행 시 time_scale 을 올리면 시뮬레이션이 빨라져 학습이 크게 단축됨.
    engine_channel = EngineConfigurationChannel()

    env = UnityEnvironment(
        file_name=cfg.get("env_path"),
        seed=cfg.get("seed", 0),
        timeout_wait=120,
        no_graphics=cfg.get("no_graphics", False),   # 빌드를 화면 없이 헤드리스 실행
        side_channels=[engine_channel],
    )
    # 게임 시계 배속. 에디터에선 제한적, 빌드에서 효과 큼. (mlagents-learn 기본도 20)
    engine_channel.set_configuration_parameters(time_scale=float(cfg.get("time_scale", 20.0)))
    env.reset()
    behavior_name = list(env.behavior_specs.keys())[0]
    spec = env.behavior_specs[behavior_name]

    # 관측이 2개(벡터 + 모기 BufferSensor)라 rank로 구분: 벡터는 1D, 모기 집합은 2D
    vec_spec = next(s for s in spec.observation_specs if len(s.shape) == 1)
    vec_dim  = vec_spec.shape[0]
    cont_dim = spec.action_spec.continuous_size
    disc_sizes = list(spec.action_spec.discrete_branches)  # 이미 브랜치 크기(int) 튜플

    model = ActorCritic(
        vec_dim      = vec_dim,
        pointnet_out = cfg["pointnet_out"],
        cont_dim     = cont_dim,
        disc_sizes   = disc_sizes,
    ).to(device)

    ppo = PPO(
        model         = model,
        lr            = cfg["lr"],
        clip_eps      = cfg["clip_eps"],
        vf_coef       = cfg["vf_coef"],
        ent_coef      = cfg["ent_coef"],
        max_grad_norm = cfg["max_grad_norm"],
        n_epochs      = cfg["n_epochs"],
        batch_size    = cfg["batch_size"],
    )

    buf = RolloutBuffer(
        buf_size  = cfg["buf_size"],
        vec_dim   = vec_dim,
        cont_dim  = cont_dim,
        n_disc    = len(disc_sizes),
        gamma     = cfg["gamma"],
        lam       = cfg["lam"],
        device    = device,
    )

    total_steps = 0
    for iteration in range(cfg["max_iterations"]):
        buf.reset()
        last_value, ep_rewards = collect_rollout(env, model, buf, device, behavior_name)
        batch = buf.get(last_value)

        losses = ppo.update(batch)
        total_steps += buf.ptr

        # TensorBoard 로깅
        writer.add_scalar("train/policy_loss", losses["policy_loss"], total_steps)
        writer.add_scalar("train/value_loss",  losses["value_loss"],  total_steps)
        writer.add_scalar("train/entropy",     losses["entropy"],     total_steps)
        if ep_rewards:
            writer.add_scalar("train/ep_reward_mean", sum(ep_rewards) / len(ep_rewards), total_steps)

        if (iteration + 1) % cfg["log_interval"] == 0:
            mean_r = sum(ep_rewards) / len(ep_rewards) if ep_rewards else float("nan")
            print(
                f"[{iteration+1:5d}] steps={total_steps:7d} | "
                f"ep_reward={mean_r:.2f} | "
                f"policy={losses['policy_loss']:.4f} | "
                f"value={losses['value_loss']:.4f} | "
                f"entropy={losses['entropy']:.4f}"
            )

        if (iteration + 1) % cfg["save_interval"] == 0:
            path = save_dir / f"model_{iteration+1}.pt"
            torch.save(
                {
                    "model":       model.state_dict(),
                    "optimizer":   ppo.optimizer.state_dict(),
                    "iteration":   iteration + 1,
                    "total_steps": total_steps,
                },
                path,
            )
            print(f"  saved → {path}")

    env.close()
    writer.close()
