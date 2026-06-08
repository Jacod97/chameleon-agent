import torch
import numpy as np


def collate_point_clouds(clouds: list[torch.Tensor], device: torch.device) -> torch.Tensor:
    """
    Args:
        clouds: 길이 B인 리스트. 각 원소는 shape [N_i, 6] (N_i는 스텝마다 다름).
        device: 결과 텐서를 올릴 디바이스.
    Returns:
        패딩된 텐서. shape [B, N_max, 6]. 빈 자리는 0으로 채움.
    """
    max_n = max(c.shape[0] for c in clouds) if clouds else 0
    if max_n == 0:
        return torch.zeros(len(clouds), 0, clouds[0].shape[-1], device=device)
    feat_dim = clouds[0].shape[-1]
    out = torch.zeros(len(clouds), max_n, feat_dim, device=device)
    for i, c in enumerate(clouds):
        if c.shape[0] > 0:
            out[i, :c.shape[0]] = c.to(device)
    return out


class RolloutBuffer:
    """
    Args:
        buf_size: 롤아웃 버퍼 최대 스텝 수.
        vec_dim: 벡터 관측 차원.
        cont_dim: 연속 행동 차원.
        n_disc: 이산 행동 브랜치 수.
        gamma: 할인율.
        lam: GAE lambda.
        device: 학습에 사용할 디바이스.
    """
    def __init__(
        self,
        buf_size: int,
        vec_dim: int,
        cont_dim: int,
        n_disc: int,
        gamma: float,
        lam: float,
        device: torch.device,
    ):
        self.buf_size = buf_size
        self.gamma = gamma
        self.lam = lam
        self.device = device

        self.vec_obs    = torch.zeros(buf_size, vec_dim)
        self.point_clouds: list[torch.Tensor] = []   # [N_i, 6] 리스트
        self.cont_acts  = torch.zeros(buf_size, cont_dim)
        self.disc_acts  = torch.zeros(buf_size, n_disc, dtype=torch.long)
        self.log_probs  = torch.zeros(buf_size)
        self.rewards    = torch.zeros(buf_size)
        self.values     = torch.zeros(buf_size)
        self.dones      = torch.zeros(buf_size)   # 에피소드 경계(종료+시간초과) → GAE 체인 리셋
        self.bootstraps = torch.zeros(buf_size)   # 경계 스텝의 V(s_{t+1}): 진짜 종료=0, 시간초과=V(terminal)

        self.ptr = 0

    def add(
        self,
        vec_obs: torch.Tensor,
        point_cloud: torch.Tensor,
        cont_act: torch.Tensor,
        disc_act: torch.Tensor,
        log_prob: torch.Tensor,
        reward: float,
        value: torch.Tensor,
        done: bool,
        bootstrap_value: float = 0.0,
    ):
        """
        Args:
            vec_obs: shape [vec_dim].
            point_cloud: shape [N, 6]. N=0도 허용.
            cont_act: shape [cont_dim].
            disc_act: shape [n_disc].
            log_prob: scalar.
            reward: float.
            value: scalar.
            done: 에피소드 경계 여부(진짜 종료 OR 시간초과). GAE 체인을 끊음.
            bootstrap_value: 경계 스텝의 V(s_{t+1}). 진짜 종료=0, 시간초과(truncated)=V(terminal obs).
                             경계가 아니면 무시됨.
        """
        i = self.ptr
        self.vec_obs[i]    = vec_obs.cpu()
        self.point_clouds.append(point_cloud.cpu())
        self.cont_acts[i]  = cont_act.cpu()
        self.disc_acts[i]  = disc_act.cpu()
        self.log_probs[i]  = log_prob.cpu()
        self.rewards[i]    = reward
        self.values[i]     = value.cpu()
        self.dones[i]      = float(done)
        self.bootstraps[i] = bootstrap_value
        self.ptr += 1

    def compute_gae(self, last_value: float):
        """
        Args:
            last_value: 버퍼 마지막 스텝이 경계가 아닐 때 쓸 다음 상태 V(s).
        Returns:
            advantages: shape [ptr].
            returns: shape [ptr].

        경계(done=True) 스텝의 다음-상태 가치는 bootstraps[t] 를 사용한다:
        진짜 종료(성공/파손)=0, 시간초과(truncated)=V(terminal obs). 어느 쪽이든
        (1-done)=0 으로 advantage 체인은 끊기지만, delta 의 bootstrap 은 유지된다
        (docs/RL_Design.md §3.4).
        """
        advantages = torch.zeros(self.ptr)
        last_gae = 0.0
        for t in reversed(range(self.ptr)):
            done = self.dones[t].item()
            if done:
                next_val = self.bootstraps[t].item()
            elif t == self.ptr - 1:
                next_val = last_value
            else:
                next_val = self.values[t + 1].item()
            delta = self.rewards[t] + self.gamma * next_val - self.values[t]
            last_gae = delta + self.gamma * self.lam * (1.0 - done) * last_gae
            advantages[t] = last_gae
        returns = advantages + self.values[:self.ptr]
        return advantages, returns

    def get(self, last_value: float):
        """
        Args:
            last_value: compute_gae에 넘길 마지막 상태 가치.
        Returns:
            dict: 미니배치 학습에 필요한 모든 텐서. point_cloud는 패딩된 [B, N_max, 6].
        """
        advantages, returns = self.compute_gae(last_value)
        advantages = (advantages - advantages.mean()) / (advantages.std() + 1e-8)

        point_cloud_batch = collate_point_clouds(self.point_clouds[:self.ptr], self.device)

        return {
            "vec_obs":     self.vec_obs[:self.ptr].to(self.device),
            "point_cloud": point_cloud_batch,
            "cont_acts":   self.cont_acts[:self.ptr].to(self.device),
            "disc_acts":   self.disc_acts[:self.ptr].to(self.device),
            "log_probs":   self.log_probs[:self.ptr].to(self.device),
            "advantages":  advantages.to(self.device),
            "returns":     returns.to(self.device),
        }

    def reset(self):
        """버퍼 초기화."""
        self.ptr = 0
        self.point_clouds.clear()
