from collections import deque

from mlagents_envs.side_channel.environment_parameters_channel import EnvironmentParametersChannel

from ._type import CurriculumStage


# 6단계 커리큘럼
STAGES = [
    CurriculumStage("1 정지·근접", mosquito_count_min=1, mosquito_count_max=1,  mosquito_stationary=1, mosquito_speed_scale=0.0, spawn_scale=0.25),
    CurriculumStage("2 정지·방전체", mosquito_count_min=1, mosquito_count_max=1,  mosquito_stationary=1, mosquito_speed_scale=0.0, spawn_scale=1.0),
    CurriculumStage("3 저속비행", mosquito_count_min=1, mosquito_count_max=1,  mosquito_stationary=0, mosquito_speed_scale=0.3, spawn_scale=1.0),
    CurriculumStage("4 정상비행", mosquito_count_min=1, mosquito_count_max=1,  mosquito_stationary=0, mosquito_speed_scale=1.0, spawn_scale=1.0),
    CurriculumStage("5 3마리", mosquito_count_min=3, mosquito_count_max=3,  mosquito_stationary=0, mosquito_speed_scale=1.0, spawn_scale=1.0),
    CurriculumStage("6 3~10마리", mosquito_count_min=3, mosquito_count_max=10, mosquito_stationary=0, mosquito_speed_scale=1.0, spawn_scale=1.0),
]

class CurriculumManager:
    """
    포획 성공률 기반 자동 단계 상승 관리.
    Trainer 는 매 iteration 의 에피소드 성공 여부만 report() 로 넘기면,
    매니저가 윈도우 성공률을 계산해 임계 도달 시 다음 단계 파라미터를 env 채널로 주입한다.
    """
    def __init__(
        self,
        channel: EnvironmentParametersChannel,
        stages: list[CurriculumStage] = None,
        threshold: float = 0.8,
        window: int = 50,
    ):
        self.channel = channel
        self.stages = stages if stages is not None else STAGES
        self.threshold = threshold
        self.window_size = window
        self._window = deque(maxlen=window)
        self._idx = 0

    def start(self):
        """학습 시작 전 1단계 파라미터 주입"""
        self._apply(self.stages[self._idx])

    def report(self, ep_successes: list) -> bool:
        """이번 iteration 의 에피소드 성공 여부를 누적. 단계 상승했으면 True."""
        self._window.extend(ep_successes)
        if self._idx < len(self.stages) - 1 and len(self._window) >= self.window_size:
            if self.success_rate >= self.threshold:
                self._idx += 1
                self._apply(self.stages[self._idx])
                self._window.clear()
                return True
        return False

    def _apply(self, stage: CurriculumStage):
        # dataclass 필드를 그대로 돌면서 채널에 주입 (하드코딩 dict 없이)
        for key, value in stage.to_params().items():
            self.channel.set_float_parameter(key, float(value))

    @property
    def success_rate(self) -> float:
        return sum(self._window) / len(self._window) if self._window else float("nan")

    @property
    def stage_index(self) -> int:
        return self._idx

    @property
    def stage_name(self) -> str:
        return self.stages[self._idx].name
