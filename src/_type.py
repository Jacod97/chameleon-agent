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
    """RolloutBuffer에서 최종 가공되어 학습에 주입될 데이터 패키지"""
    observation_vector: torch.Tensor
    point_clouds: torch.Tensor
    continuous_actions: torch.Tensor
    discrete_actions: torch.Tensor
    log_probs: torch.Tensor
    advantages: torch.Tensor
    target_values: torch.Tensor 

@dataclass
class PPOResult:
    """PPO의 1회 update 세션 동안 계산된 평균 손실 및 지표"""
    policy_loss: float
    value_loss: float
    entropy: float