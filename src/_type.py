import torch
from dataclasses import dataclass, asdict

@dataclass
class CurriculumStage:
    """커리큘럼 한 단계. 필드명 = Unity EnvironmentParameters 키와 1:1 대응."""
    name: str
    mosquito_count_min: float
    mosquito_count_max: float
    mosquito_stationary: float
    mosquito_speed_scale: float
    spawn_scale: float

    def to_params(self) -> dict:
        """name 을 제외한 난이도 파라미터 dict (channel 에 그대로 주입)."""
        params = asdict(self)
        params.pop("name")
        return params

@dataclass
class RolloutBatch:
    """RolloutBuffer에서 최종 가공되어 학습에 주입될 데이터 패키지.
    continuous 행동은 pre-tanh u 로 저장 — evaluate 에서 atanh 역연산 없이 정확 재계산"""
    observation_vector: torch.Tensor
    point_clouds: torch.Tensor
    pre_tanh_actions: torch.Tensor
    discrete_actions: torch.Tensor
    log_probs: torch.Tensor
    advantages: torch.Tensor
    target_values: torch.Tensor

@dataclass
class PPOResult:
    """PPO의 1회 update 세션 동안 계산된 평균 손실 및 지표.
    entropy 는 연속/이산 분리 — 이산(발사) 탐색 붕괴를 따로 모니터링"""
    policy_loss: float = 0.0
    value_loss: float = 0.0
    entropy_continuous: float = 0.0
    entropy_discrete: float = 0.0
    approx_kl: float = 0.0
    clip_fraction: float = 0.0
    explained_variance: float = 0.0

    def averaged(self, steps: int) -> "PPOResult":
        """미니배치 합산값을 update 횟수로 나눈 평균"""
        return PPOResult(**{k: v / steps for k, v in asdict(self).items()})