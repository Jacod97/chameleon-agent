import torch
import torch.nn as nn
from torch.utils.data import DataLoader, TensorDataset


class PPO:
    """
    Args:
        model: ActorCritic 네트워크.
        lr: Adam 학습률.
        clip_eps: PPO 클립 범위 epsilon.
        vf_coef: 가치 함수 손실 계수.
        ent_coef: 엔트로피 보너스 계수.
        max_grad_norm: 그래디언트 클리핑 임계값.
        n_epochs: 버퍼당 업데이트 횟수.
        batch_size: 미니배치 크기.
    """
    def __init__(
        self,
        model: nn.Module,
        lr: float,
        clip_eps: float,
        vf_coef: float,
        ent_coef: float,
        max_grad_norm: float,
        n_epochs: int,
        batch_size: int,
    ):
        self.model         = model
        self.clip_eps      = clip_eps
        self.vf_coef       = vf_coef
        self.ent_coef      = ent_coef
        self.max_grad_norm = max_grad_norm
        self.n_epochs      = n_epochs
        self.batch_size    = batch_size
        self.optimizer     = torch.optim.Adam(model.parameters(), lr=lr)

    def update(self, batch: dict) -> dict:
        """
        Args:
            batch: RolloutBuffer.get()이 반환한 딕셔너리.
                   keys: vec_obs, point_cloud, cont_acts, disc_acts,
                         log_probs (old), advantages, returns.
        Returns:
            losses: 로깅용 손실 딕셔너리.
                    keys: policy_loss, value_loss, entropy, total_loss.
        """
        vec_obs     = batch["vec_obs"]
        point_cloud = batch["point_cloud"]
        cont_acts   = batch["cont_acts"]
        disc_acts   = batch["disc_acts"]
        old_log_prob = batch["log_probs"]
        advantages  = batch["advantages"]
        returns     = batch["returns"]

        n = vec_obs.shape[0]
        idx = torch.arange(n, device=vec_obs.device)

        total_pl, total_vl, total_ent = 0.0, 0.0, 0.0

        for _ in range(self.n_epochs):
            perm = idx[torch.randperm(n)]
            for start in range(0, n, self.batch_size):
                mb = perm[start:start + self.batch_size]

                # point_cloud 슬라이싱: 패딩 텐서 그대로 인덱싱
                mb_pc = point_cloud[mb]

                log_prob, entropy, value = self.model.evaluate(
                    vec_obs[mb], mb_pc, cont_acts[mb], disc_acts[mb]
                )

                # PPO 클립 손실
                ratio = (log_prob - old_log_prob[mb]).exp()
                adv   = advantages[mb]
                surr1 = ratio * adv
                surr2 = ratio.clamp(1.0 - self.clip_eps, 1.0 + self.clip_eps) * adv
                policy_loss = -torch.min(surr1, surr2).mean()

                # 가치 함수 손실
                value_loss = (returns[mb] - value).pow(2).mean()

                # 엔트로피 보너스
                entropy_loss = -entropy.mean()

                loss = policy_loss + self.vf_coef * value_loss + self.ent_coef * entropy_loss

                self.optimizer.zero_grad()
                loss.backward()
                nn.utils.clip_grad_norm_(self.model.parameters(), self.max_grad_norm)
                self.optimizer.step()

                total_pl  += policy_loss.item()
                total_vl  += value_loss.item()
                total_ent += entropy.mean().item()

        n_minibatches = (n + self.batch_size - 1) // self.batch_size  # ceil, 마지막 부분 배치 포함
        steps = self.n_epochs * max(1, n_minibatches)
        return {
            "policy_loss": total_pl  / steps,
            "value_loss":  total_vl  / steps,
            "entropy":     total_ent / steps,
            "total_loss":  (total_pl + self.vf_coef * total_vl + self.ent_coef * (-total_ent)) / steps,
        }
