import torch
from mlagents_envs.base_env import ActionTuple

# ChameleonAgent.CollectObservations 의 "남은 모기 수 / 10" 위치 (벡터 관측 6번)
REMAINING_OBS_INDEX = 6
REMAINING_OBS_SCALE = 10.0

class UnityCommunicator:
    def __init__(self, env, behavior_name, device):
        self.env = env
        self.behavior_name = behavior_name
        self.device = device
        # agent_id → 에피소드 시작 시점 모기 수. 포획률(잡은 수/스폰 수) 계산용.
        # collect() 호출(iteration) 경계를 넘어 에피소드가 이어지므로 인스턴스에 유지.
        self._ep_spawn: dict[int, int] = {}

    def collect(self, model, buf):
        model.eval()
        ep_rewards = []
        ep_successes = []
        ep_lengths = []
        ep_timeouts = []
        ep_reward_by_agent: dict[int, float] = {}  # 에이전트별 누적 — 병렬 에이전트 보상 혼합 방지
        ep_len_by_agent: dict[int, int] = {}
        last_vals: dict[int, float] = {}           # agent_id → 마지막 value (에이전트별 독립 bootstrap)
        pending: dict[int, dict] = {}

        while buf.pointer < buf.buffer_size:
            dec_steps, term_steps = self.env.get_steps(self.behavior_name)

            for agent_id in term_steps.agent_id:
                aid = int(agent_id)
                p = pending.pop(aid, None)
                if p is None:
                    continue
                ts = term_steps[agent_id]
                reward = float(ts.reward)
                interrupted = bool(ts.interrupted)
                bootstrap_val = self._get_bootstrap_val(model, ts) if interrupted else 0.0
                ep_reward_by_agent[aid] = ep_reward_by_agent.get(aid, 0.0) + reward
                last_vals[aid] = bootstrap_val
                buf.add(
                    observation_vector=p["vec"],
                    point_cloud=p["pt"],
                    pre_tanh_action=p["pre_tanh"],
                    discrete_action=p["disc"],
                    log_prob=p["log_prob"],
                    reward=reward,
                    value=p["value"],
                    done=True,
                    agent_id=aid,
                    bootstrap_value=bootstrap_val,
                )
                # 성공 지표 = 포획률(잡은 수/스폰 수). "전멸 여부"는 마리 수가 늘수록
                # 난이도가 거듭제곱으로 커져 커리큘럼이 정체됨 — 보이는 모기를 잡는
                # 실력 자체를 평가한다 (타임아웃이라도 다 잡았으면 1.0)
                spawn0 = self._ep_spawn.pop(aid, 0)
                if spawn0 > 0:
                    remaining = self._read_remaining(ts.obs)
                    catch_rate = min(1.0, max(0.0, (spawn0 - remaining) / spawn0))
                else:
                    # 스폰 수 미기록(이론상 도달 불가) — 기존 전멸 판정으로 폴백
                    catch_rate = 1.0 if (not interrupted) and (reward > 0.0) else 0.0
                ep_successes.append(catch_rate)
                ep_rewards.append(ep_reward_by_agent[aid])
                ep_reward_by_agent[aid] = 0.0
                ep_lengths.append(ep_len_by_agent.pop(aid, 0) + 1)
                ep_timeouts.append(interrupted)
                if buf.pointer >= buf.buffer_size:
                    break
            if buf.pointer >= buf.buffer_size:
                break

            if len(dec_steps) > 0:
                vec_obs, pt_obs = self._split_obs(dec_steps.obs)
                with torch.no_grad():
                    cont_acts, pre_tanh, disc_acts, log_probs, values = model.get_action(vec_obs, pt_obs)

                full = False
                for i, agent_id in enumerate(dec_steps.agent_id):
                    aid = int(agent_id)
                    # 에피소드 첫 관측에서 스폰 수 기록 (terminal 처리 시 pop 됨).
                    # 이미 기록돼 있으면 진행 중인 에피소드 — 덮어쓰면 중간 포획분이 누락됨
                    if aid not in self._ep_spawn:
                        self._ep_spawn[aid] = int(round(
                            vec_obs[i, REMAINING_OBS_INDEX].item() * REMAINING_OBS_SCALE))
                    p = pending.pop(aid, None)
                    if p is not None and not full:
                        reward = float(dec_steps[agent_id].reward)
                        ep_reward_by_agent[aid] = ep_reward_by_agent.get(aid, 0.0) + reward
                        ep_len_by_agent[aid] = ep_len_by_agent.get(aid, 0) + 1
                        last_vals[aid] = values[i].item()
                        buf.add(
                            observation_vector=p["vec"],
                            point_cloud=p["pt"],
                            pre_tanh_action=p["pre_tanh"],
                            discrete_action=p["disc"],
                            log_prob=p["log_prob"],
                            reward=reward,
                            value=p["value"],
                            done=False,
                            agent_id=aid,
                            bootstrap_value=0.0,
                        )
                        if buf.pointer >= buf.buffer_size:
                            full = True
                    pending[aid] = {
                        "vec": vec_obs[i],
                        "pt": pt_obs[i],
                        "pre_tanh": pre_tanh[i],
                        "disc": disc_acts[i],
                        "log_prob": log_probs[i],
                        "value": values[i],
                    }

                self.env.set_actions(self.behavior_name, ActionTuple(
                    continuous=cont_acts.cpu().numpy(),
                    discrete=disc_acts.cpu().numpy().astype("int32"),
                ))

            self.env.step()

        model.train()
        return last_vals, ep_rewards, ep_successes, ep_lengths, ep_timeouts

    def _split_obs(self, obs_list):
        vec_np = next(o for o in obs_list if o.ndim == 2)
        pt_cands = [o for o in obs_list if o.ndim == 3]

        vec_t = torch.tensor(vec_np, dtype=torch.float32, device=self.device)
        if pt_cands:
            pt_t = torch.tensor(pt_cands[0], dtype=torch.float32, device=self.device)
        else:
            pt_t = torch.zeros(vec_t.shape[0], 0, 6, device=self.device)

        return vec_t, pt_t

    def _read_remaining(self, obs_list):
        """terminal step 관측에서 남은 모기 수 복원"""
        vec = next(o for o in obs_list if o.ndim == 1)
        return int(round(float(vec[REMAINING_OBS_INDEX]) * REMAINING_OBS_SCALE))

    def _get_bootstrap_val(self, model, term_step):
        vec_np = next(o for o in term_step.obs if o.ndim == 1)
        pt_cands = [o for o in term_step.obs if o.ndim == 2]

        vec_t = torch.tensor(vec_np[None, ...], dtype=torch.float32, device=self.device)

        if pt_cands:
            pt_t = torch.tensor(pt_cands[0][None, ...], dtype=torch.float32, device=self.device)
        else:
            pt_t = torch.zeros(1, 0, 6, device=self.device)

        with torch.no_grad():
            return model.get_value(vec_t, pt_t)[0].item()
