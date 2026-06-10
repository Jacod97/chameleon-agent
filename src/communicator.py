import torch
from mlagents_envs.base_env import ActionTuple

class UnityCommunicator:
    def __init__(self, env, behavior_name, device):
        self.env = env
        self.behavior_name = behavior_name
        self.device = device

    def collect(self, model, buf):
        model.eval()
        ep_rewards = []
        ep_successes = []
        ep_reward_by_agent: dict[int, float] = {}  # 에이전트별 누적 — 병렬 에이전트 보상 혼합 방지
        last_vals: dict[int, float] = {}           # agent_id → 마지막 value (에이전트별 독립 bootstrap)

        while buf.pointer < buf.buffer_size:
            dec_steps, _ = self.env.get_steps(self.behavior_name)

            if len(dec_steps) == 0:
                self.env.step()
                continue

            vec_obs, pt_obs = self._split_obs(dec_steps.obs)

            with torch.no_grad():
                cont_acts, pre_tanh, disc_acts, log_probs, values = model.get_action(vec_obs, pt_obs)

            cont_np = cont_acts.cpu().numpy()
            disc_np = disc_acts.cpu().numpy().astype("int32")

            self.env.set_actions(self.behavior_name, ActionTuple(continuous=cont_np, discrete=disc_np))
            self.env.step()

            next_dec, next_term = self.env.get_steps(self.behavior_name)

            for i, agent_id in enumerate(dec_steps.agent_id):
                aid = int(agent_id)
                interrupted = False
                if agent_id in next_term:
                    ts = next_term[agent_id]
                    reward = float(ts.reward)
                    done = True
                    interrupted = bool(ts.interrupted)
                    bootstrap_val = self._get_bootstrap_val(model, ts) if interrupted else 0.0
                elif agent_id in next_dec:
                    reward = float(next_dec[agent_id].reward)
                    done = False
                    bootstrap_val = 0.0
                else:
                    # 액션을 보낸 에이전트가 다음 스텝에 흔적 없이 사라짐 — 정상 경로 아님
                    raise RuntimeError(
                        f"agent {aid} 가 next_dec/next_term 어디에도 없음 — "
                        f"환경 step 동기화 또는 에이전트 등록 문제")

                ep_reward_by_agent[aid] = ep_reward_by_agent.get(aid, 0.0) + reward

                # 에이전트별 마지막 value 갱신 (GAE에서 각 에이전트 trajectory 끝 bootstrap에 사용)
                if done:
                    last_vals[aid] = bootstrap_val
                else:
                    last_vals[aid] = values[i].item()

                buf.add(
                    observation_vector=vec_obs[i],
                    point_cloud=pt_obs[i],
                    pre_tanh_action=pre_tanh[i],
                    discrete_action=disc_acts[i],
                    log_prob=log_probs[i],
                    reward=reward,
                    value=values[i],
                    done=done,
                    agent_id=aid,
                    bootstrap_value=bootstrap_val,
                )

                if done:
                    ep_successes.append((not interrupted) and (reward > 0.0))
                    ep_rewards.append(ep_reward_by_agent[aid])
                    ep_reward_by_agent[aid] = 0.0

                if buf.pointer >= buf.buffer_size:
                    break

        model.train()
        return last_vals, ep_rewards, ep_successes

    def _split_obs(self, obs_list):
        vec_np = next(o for o in obs_list if o.ndim == 2)
        pt_cands = [o for o in obs_list if o.ndim == 3]

        vec_t = torch.tensor(vec_np, dtype=torch.float32, device=self.device)
        if pt_cands:
            pt_t = torch.tensor(pt_cands[0], dtype=torch.float32, device=self.device)
        else:
            pt_t = torch.zeros(vec_t.shape[0], 0, 6, device=self.device)

        return vec_t, pt_t

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
