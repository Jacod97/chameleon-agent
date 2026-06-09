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
        ep_successes = []     # 에피소드별 전멸 성공 여부 (커리큘럼 졸업 판정용)
        ep_reward = 0.0
        last_val = 0.0

        while buf.pointer < buf.buffer_size:
            dec_steps, _ = self.env.get_steps(self.behavior_name)
            
            # 액션을 취할 에이전트가 없으면 환경만 1스텝 넘김
            if len(dec_steps) == 0:
                self.env.step()
                continue

            # 관측치(obs) 처리
            vec_obs, pt_obs = self._split_obs(dec_steps.obs)
            
            with torch.no_grad():
                cont_acts, disc_acts, log_probs, values = model.get_action(vec_obs, pt_obs)

            # Unity 환경에 보낼 액션 포맷팅 (disc_acts 는 이미 [B, n_branches])
            cont_np = cont_acts.cpu().numpy()
            disc_np = disc_acts.cpu().numpy().astype("int32")
            
            self.env.set_actions(self.behavior_name, ActionTuple(continuous=cont_np, discrete=disc_np))
            self.env.step()

            # 환경 진행 후 다음 스텝 상태 받아오기
            next_dec, next_term = self.env.get_steps(self.behavior_name)
            
            for i, agent_id in enumerate(dec_steps.agent_id):
                interrupted = False
                # 1. 에피소드 종료 (Terminal)
                if agent_id in next_term:
                    ts = next_term[agent_id]
                    reward = float(ts.reward)
                    done = True
                    interrupted = bool(ts.interrupted)
                    # 타임아웃 등으로 잘렸다면 가치함수로 부트스트랩
                    bootstrap_val = self._get_bootstrap_val(model, ts) if interrupted else 0.0
                
                # 2. 에피소드 진행 중 (Decision)
                elif agent_id in next_dec:
                    reward = float(next_dec[agent_id].reward)
                    done = False
                    bootstrap_val = 0.0
                
                # 3. 예외 상황
                else:
                    reward, done, bootstrap_val = 0.0, False, 0.0

                ep_reward += reward
                
                # 버퍼에 1스텝 분량의 데이터 저장
                buf.add(
                    observation_vector=vec_obs[i],
                    point_cloud=pt_obs[i],
                    continuous_action=cont_acts[i],
                    discrete_action=disc_acts[i],
                    log_prob=log_probs[i],
                    reward=reward,
                    value=values[i],
                    done=done,
                    bootstrap_value=bootstrap_val,
                )
                
                # 에피소드 정산
                if done:
                    # 비중단(MaxStep 아님) 종료 + 양수 종단보상 = 전멸 성공
                    ep_successes.append((not interrupted) and (reward > 0.0))
                    ep_rewards.append(ep_reward)
                    ep_reward = 0.0
                    last_val = 0.0
                else:
                    last_val = values[i].item()

                if buf.pointer >= buf.buffer_size:
                    break

        model.train()
        return last_val, ep_rewards, ep_successes

    def _split_obs(self, obs_list):
        """다중 obs 리스트에서 1D 벡터와 2D 포인트 클라우드 분리 (배치 차원 포함)"""
        vec_np = next(o for o in obs_list if o.ndim == 2)
        pt_cands = [o for o in obs_list if o.ndim == 3]
        
        vec_t = torch.tensor(vec_np, dtype=torch.float32, device=self.device)
        if pt_cands:
            pt_t = torch.tensor(pt_cands[0], dtype=torch.float32, device=self.device)
        else:
            pt_t = torch.zeros(vec_t.shape[0], 0, 6, device=self.device)
            
        return vec_t, pt_t

    def _get_bootstrap_val(self, model, term_step):
        """잘린 에피소드의 마지막 가치(Value) 예측"""
        vec_np = next(o for o in term_step.obs if o.ndim == 1)
        pt_cands = [o for o in term_step.obs if o.ndim == 2]
        
        # None을 활용한 파이토치 관용적 차원 추가 기법 (unsqueeze와 동일)
        vec_t = torch.tensor(vec_np[None, ...], dtype=torch.float32, device=self.device)
        
        if pt_cands:
            pt_t = torch.tensor(pt_cands[0][None, ...], dtype=torch.float32, device=self.device)
        else:
            pt_t = torch.zeros(1, 0, 6, device=self.device)
            
        with torch.no_grad():
            return model.get_value(vec_t, pt_t)[0].item()