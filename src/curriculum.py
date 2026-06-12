from collections import deque

from mlagents_envs.side_channel.environment_parameters_channel import EnvironmentParametersChannel

from ._type import CurriculumStage


# 8단계 커리큘럼 — 난이도 점프 구간(저속→정상 속도, 1마리→3마리)마다 중간 단계 삽입
STAGES = [
    CurriculumStage("1 정지·근접", mosquito_count_min=1, mosquito_count_max=1,  mosquito_stationary=1, mosquito_speed_scale=0.0, spawn_scale=0.25),
    CurriculumStage("2 정지·방전체", mosquito_count_min=1, mosquito_count_max=1,  mosquito_stationary=1, mosquito_speed_scale=0.0, spawn_scale=1.0),
    CurriculumStage("3 저속비행", mosquito_count_min=1, mosquito_count_max=1,  mosquito_stationary=0, mosquito_speed_scale=0.3, spawn_scale=1.0),
    CurriculumStage("4 중속비행", mosquito_count_min=1, mosquito_count_max=1,  mosquito_stationary=0, mosquito_speed_scale=0.6, spawn_scale=1.0),
    CurriculumStage("5 정상비행", mosquito_count_min=1, mosquito_count_max=1,  mosquito_stationary=0, mosquito_speed_scale=1.0, spawn_scale=1.0),
    CurriculumStage("6 2마리", mosquito_count_min=2, mosquito_count_max=2,  mosquito_stationary=0, mosquito_speed_scale=1.0, spawn_scale=1.0),
    CurriculumStage("7 3마리", mosquito_count_min=3, mosquito_count_max=3,  mosquito_stationary=0, mosquito_speed_scale=1.0, spawn_scale=1.0),
    CurriculumStage("8 3~10마리", mosquito_count_min=3, mosquito_count_max=10, mosquito_stationary=0, mosquito_speed_scale=1.0, spawn_scale=1.0),
]

class CurriculumManager:
    """
    포획률 기반 자동 단계 상승 관리.
    Trainer 는 매 iteration 의 에피소드별 포획률(잡은 수/스폰 수, 0~1)을 report() 로 넘기면,
    매니저가 윈도우 평균을 계산해 임계 도달 시 다음 단계 파라미터를 env 채널로 주입한다.
    "전멸 여부" 대신 포획률을 쓰는 이유: 전멸 기준은 마리 수 n 에 대해 난이도가
    마리당 실력의 n제곱으로 커져 다마리 단계에서 커리큘럼이 영구 정체된다.
    """
    def __init__(
        self,
        channel: EnvironmentParametersChannel,
        stages: list[CurriculumStage] = None,
        threshold: float = 0.8,
        window: int = 50,
        start_index: int = 0,
    ):
        self.channel = channel
        self.stages = stages if stages is not None else STAGES
        self.threshold = threshold
        self.window_size = window
        self._window = deque(maxlen=window)
        self._idx = max(0, min(start_index, len(self.stages) - 1))
        self._last_advance_rate = float("nan")

    def start(self):
        """학습 시작 전 1단계 파라미터 주입"""
        self._apply(self.stages[self._idx])

    def report(self, ep_successes: list) -> bool:
        """이번 iteration 의 에피소드별 포획률(0~1)을 누적. 단계 상승했으면 True."""
        self._window.extend(ep_successes)
        if self._idx < len(self.stages) - 1 and len(self._window) >= self.window_size:
            if self.success_rate >= self.threshold:
                self._last_advance_rate = self.success_rate
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
    def last_advance_rate(self) -> float:
        return self._last_advance_rate

    @property
    def stage_index(self) -> int:
        return self._idx

    @property
    def stage_name(self) -> str:
        return self.stages[self._idx].name
