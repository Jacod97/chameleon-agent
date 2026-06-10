# 설계 검토 보고서 — 학습 안정성 관점 전수 검사

> 검토 범위: 학습에 영향을 주는 모든 코드.
> C# 런타임 스크립트 7개 전체, Python 학습 코드 전체, 씬 설정(DecisionRequester, BehaviorParameters, BufferSensor),
> 모기 프리팹, 프리팹 생성 에디터 스크립트, 보상 설정 에셋.
> (제외: 시각화 전용 에디터 스크립트 2개, Unity 템플릿 TutorialInfo — 학습 무관 확인 후 제외)

## 확정된 환경 설정

| 항목 | 값 | 의미 |
|------|----|------|
| DecisionPeriod | 5 | 결정 1회 = FixedUpdate 5회 (0.1초) |
| TakeActionsBetweenDecisions | 1 | 결정 사이에도 마지막 행동 반복 실행 |
| MaxStep | 3000 | 에피소드 최대 60 게임초 = 600 결정 |
| 벡터 관측 | 7 → **9 dim** (수정) | 아래 A-1, A-2 |
| BufferSensor | 최대 10 × 6 | 모기 관측 (패딩 자동) |
| 모기 콜라이더 | 반경 5mm, Trigger | 표면 5mm 위 착지 |
| 병렬 에이전트 | 4 | 단일 버퍼에 섞여 수집 |

---

## A. 상태 관측 결함 (MDP 위반)

### A-1. 혀 상태가 관측에 없음 — ✅ 수정됨

혀 사이클 0.3초 = 3 decision 동안 발사 명령이 무효인데 에이전트가 알 방법이 없었다.
같은 관측에서 "발사 → 잡힘"과 "발사 → 무시됨"이 무작위로 갈리면 가치 추정이 원리적으로 불가능하다.

**수정:** 관측에 혀 준비 플래그 1-dim 추가 (`Idle=1, 사이클 중=0`). `ChameleonAgent.cs`

### A-2. 정밀 보너스가 예측 불가능한 보상이었음 — ✅ 수정됨

`precisionBonus(+2)`는 에피소드 내 헛스윙 0회일 때만 지급되는데, "헛스윙했는지"가 관측에 없었다.
마지막 모기를 잡기 직전 상태에서 가치함수가 +2를 받을지 못 받을지 알 수 없어
value loss가 끝까지 내려가지 않고 advantage에 상시 노이즈가 낀다.

**수정:** 무실수 플래그 1-dim 추가 (`misses==0 → 1`). 벡터 관측 7 → 9 dim, 씬 4곳 갱신.

### A-3. 머리 yaw 무제한 회전 + 관측 불연속 — ✅ 수정됨

yaw가 clamp 없이 무한 회전 가능했고, 관측값 `yaw/180`이 ±180° 경계에서 +1 → −1로 점프했다.
신경망은 이 불연속 경계에서 가치를 잘못 일반화한다.

**수정:** `yawClamp = ±90°` 추가 (pitch와 동일 방식), 관측 정규화도 clamp 기준으로 변경.

---

## B. 시뮬레이션 충실도

### B-1. 모기가 렌더 프레임에서 이동 — ✅ 수정됨 (가장 심각)

물리·관측·혀 판정은 전부 FixedUpdate 기반인데 모기만 `Update()`(렌더 프레임)에서 움직였다.

$$\text{time\_scale } 20 \times \frac{1}{60}\text{초} \approx 0.33\text{ 게임초/프레임} \;\Rightarrow\; \text{모기 1m/s 기준 프레임당 } 0.33\text{m 점프}$$

에이전트 입장에서 모기는 몇 decision 동안 정지해 있다가 순간이동하는 표적이었다.
속도 관측과 실제 거동도 어긋난다. **time_scale 20 빌드에서 학습 데이터 자체가 왜곡되는 문제.**

**수정:** `Mosquito.Update → FixedUpdate`, `Time.deltaTime → Time.fixedDeltaTime`.

### B-2. 잡힌 모기가 0.3초간 유령으로 잔존 + 보상 지연 — ✅ 수정됨

포획 판정은 발사 순간(SphereCast) 확정인데, 보상 지급·모기 제거는 15 fixed step 뒤(`FinishCycle`)였다.
그동안 잡힌 모기가 관측에 남고(혀끝에 끌려오는 위치 + 낡은 속도), 행동-보상 인과가 3 decision 어긋났다.
리스트 정리도 렌더 프레임 `Update` 의존이라 time_scale 20에서 AliveCount·전멸 판정이 추가 지연됐다.

**수정:**
- 보상(catch/miss)을 발사 순간 즉시 지급
- `MosquitoSpawner.Remove()` 신설 — 포획 즉시 동기 제거 (렌더 프레임 정리 코드 삭제)
- 잡힌 모기는 `MarkCaught()`로 이동·콜라이더 비활성, 시각 잔상만 혀끝 견인
- 에피소드 중단 시 견인 중이던 시각 오브젝트 정리 (`TongueController.ResetState`)
- 부수 효과: 마지막 모기 포획 시 catch + success + precision이 **같은 스텝**에 들어와 credit 할당이 깨끗해짐

### B-3. 착지한 모기는 사실상 포획 불가 — ✅ 수정됨

모기 콜라이더는 반경 5mm이고 표면 5mm 위에 착지한다. 포획 SphereCast 반경이 0.15라서
바닥·가구를 거의 항상 먼저 맞았다 → 정조준해도 miss 처리, 가구였다면 `adhesionImpulse(4)`로
끌어당겨 2차 충돌 파손(−5 종료)까지 유발할 수 있었다.

**수정:** 모기 레이어 우선 SphereCast → 명중 시 가는 ray로 차폐 확인(벽 뒤 모기 관통 방지)
→ 실패 시에만 장애물 대상 캐스트(시각화·흡착용).

---

## C. 보상 설계

### C-1. 접근 보상이 시간 패널티에 묻힘 — ✅ 수정됨

decision당 시간 패널티 $0.001 \times 5 = 0.005$ vs 접근 보상 최대 $0.01 \times 0.15\text{m} = 0.0015$.
전속력으로 모기에 돌진해도 시간 패널티의 30%밖에 못 벌어 shaping이 사실상 죽어 있었다.

**수정:** `approachCoeff` $0.01 \to 0.05$. 3m 전진 시 누적 $+0.15$로 catch($1.0$)보다 충분히 작아 안전.

### C-2. 정밀 보너스 + miss 패널티 = 발사 기피 증폭 — ✅ 수정됨 (D-4와 함께)

"쏘면 −0.05 위험 + precision +2 영구 상실, 안 쏘면 무손실" 구조라 발사 회피로 이중 압력이 걸렸다.
이산 entropy가 합산에 묻히는 문제(D-4)와 결합하면 발사 정책이 조기에 "대기"로 굳을 위험.

**수정:** D-4의 이산 entropy 계수 분리로 대응. `entropy_discrete` 지표를 별도 로깅하므로
0.1 미만으로 떨어지면 발사 탐색이 굳은 것 — `ent_coef_disc` 상향 또는 `precisionBonus` 하향으로 조정.

### C-3. (잔존, 모니터링 항목) Terminal 보상 집중 → advantage 정규화 지배

성공 스텝에 catch+success+precision $= +4$가 몰리면 배치 정규화 기준 std가 커져
중간 스텝(접근 보상)의 정규화 후 advantage가 0 근처로 압사된다.
접근 보상 상향(C-1)으로 완화됐지만 구조는 남아 있다. 학습이 정체되면
successBonus/precisionBonus를 줄이거나 reward 분배(모기당 즉시 지급 비중 확대)를 검토.

---

## D. 학습 코드 (Python)

### D-1. 병렬 에이전트 GAE 크로스 오염 — ✅ 수정됨 (이전 라운드)

4개 에이전트 transition이 단일 버퍼에 섞여 `values[t+1]`이 다른 에이전트의 가치를 참조했다.
에이전트 ID별 trajectory 분리 계산으로 수정. `buffer.py`, `communicator.py`

### D-2. ep_reward가 4개 에이전트에 걸쳐 합산 — ✅ 수정됨

`ep_reward` 단일 변수에 모든 에이전트 보상이 누적되어 `ep_reward_mean` 지표가 무의미했다
(커리큘럼 판정은 `ep_successes` 기반이라 무사). 에이전트별 dict로 분리.

### D-3. atanh 경계 수치 불안정 — ✅ 수정됨

$\tanh(u)$를 저장했다가 $\text{atanh}(\text{clamp}(\cdot))$로 복원하는 경로는 $\pm 1$ 경계에서
수치 오차로 log prob이 튀어 PPO ratio가 clip 범위를 무력화할 수 있었다.

**수정:** 샘플링 시점의 pre-tanh $u$를 버퍼에 그대로 저장, `evaluate`에서 역연산 없이 사용.
`network.py`, `buffer.py`, `ppo.py`, `communicator.py`, `_type.py`

### D-4. 이산 entropy가 연속에 묻힘 — ✅ 수정됨

$$c_e \cdot (H_{cont} + H_{disc}), \qquad H_{cont} \text{(4차원 합)} \gg H_{disc} \le \ln 2$$

발사/대기 탐색 유지 인센티브가 사실상 0이었다.

**수정:** entropy를 연속/이산 분리 반환, 별도 계수 적용 (`ent_coef=0.003`, `ent_coef_disc=0.01`).
両방 모두 MLflow에 별도 지표로 로깅.

### D-5. 조용한 예외 처리 — ✅ 수정됨

에이전트가 next_dec/next_term 어디에도 없으면 보상 0으로 조용히 진행하던 분기를
`RuntimeError`로 변경 (fail-fast).

---

## E. 커리큘럼

### E-1. Stage 2 도달 불가능 스폰 → 영구 정체 위험 — ✅ 수정됨

혀 최대 도달 높이:

$$h_{muzzle} + 2.5 \times \sin 60° \approx h_{muzzle} + 2.17\text{m}$$

정지 모기가 y ≤ 2.5 코너에 스폰되면 도달 가능 영역이 극히 좁거나 불가능하고,
**정지 상태라 영원히 안 내려온다.** 이런 에피소드 비율이 임계(0.8)를 구조적으로 막으면
커리큘럼이 영구 정체된다.

**수정:** 정지 단계에 한해 스폰 높이 상한 `stationaryMaxSpawnY = 1.8` 적용. `MosquitoSpawner.cs`

### E-2. (잔존, 실험 후 판단) Stage 4→5 모기 수 1→3 점프

사용자 판단으로 보류 — 실험에서 stage 5 진입 후 성공률이 장기 정체되면 2마리 중간 단계 삽입.

---

## 이전 라운드 수정 항목 (참고)

| 항목 | 파일 |
|------|------|
| 속도 관측 월드→로컬 좌표계 + 정규화 스케일 0.5 | `ChameleonAgent.cs` |
| 혀 사이클 Update→FixedUpdate (에피소드 경계 오염) | `TongueController.cs` |
| BufferSensor 모기 속도 정규화 (`maxMosquitoSpeed`) | `MosquitoSensor.cs` |
| 정밀 사격 보너스 추가 | `RewardConfig.cs`, `ChameleonAgent.cs` |

---

## ⚠ 재학습 필요

- 벡터 관측 7 → 9 dim: **기존 체크포인트 호환 불가**, 처음부터 재학습
- Unity 에디터에서 Inspector 값이 prefab/씬에 저장된 경우 새 기본값(`velocityNormScale=0.5`,
  `approachCoeff`는 에셋에 반영됨)이 덮어써지지 않았는지 확인 필요

## 모니터링 가이드

| 지표 | 정상 | 경고 신호 |
|------|------|----------|
| `entropy_discrete` | 0.3~0.69에서 서서히 감소 | 초반 50 iter 내 0.1 미만 → 발사 기피 고착, `ent_coef_disc` 상향 |
| `value_loss` | 꾸준히 감소 | 정체 시 C-3 (terminal 집중) 의심 |
| `success_rate` | 단계당 수십~수백 iter 내 0.8 도달 | stage 2에서 장기 정체 → 스폰 캡 추가 하향 (1.8 → 1.5) |
| `ep_reward_mean` | 단계 진입 직후 하락 후 회복 | 회복 없으면 해당 단계 난이도 점프 과대 |

## 결과
```
[curriculum] start stage: 5 3마리
[   10] stage=5 steps= 102400 | ep_reward=0.11 | succ=0.38 | len=464 timeout=0.38 | policy=-0.0017 value=0.1315 ent_c=5.3879 ent_d=0.0064 | kl=0.0038 clip=0.04 ev=0.38
[   20] stage=5 steps= 204800 | ep_reward=-2.31 | succ=0.44 | len=948 timeout=0.67 | policy=0.0000 value=0.0416 ent_c=5.3857 ent_d=0.0031 | kl=0.0059 clip=0.06 ev=0.50
[   30] stage=5 steps= 307200 | ep_reward=-2.99 | succ=0.38 | len=839 timeout=0.70 | policy=-0.0009 value=0.0501 ent_c=5.3927 ent_d=0.0029 | kl=0.0036 clip=0.03 ev=0.33
[   40] stage=5 steps= 409600 | ep_reward=-2.11 | succ=0.38 | len=800 timeout=0.70 | policy=-0.0006 value=0.0341 ent_c=5.3774 ent_d=0.0055 | kl=0.0069 clip=0.09 ev=0.64
[   50] stage=5 steps= 512000 | ep_reward=-3.25 | succ=0.38 | len=770 timeout=0.55 | policy=0.0020 value=0.0805 ent_c=5.3806 ent_d=0.0068 | kl=0.0075 clip=0.07 ev=0.21
[   60] stage=5 steps= 614400 | ep_reward=-1.09 | succ=0.38 | len=600 timeout=0.53 | policy=-0.0005 value=0.0727 ent_c=5.3857 ent_d=0.0056 | kl=0.0048 clip=0.05 ev=0.50
[   70] stage=5 steps= 716800 | ep_reward=-0.94 | succ=0.32 | len=728 timeout=0.50 | policy=-0.0010 value=0.0459 ent_c=5.3699 ent_d=0.0049 | kl=0.0053 clip=0.06 ev=0.57
[   80] stage=5 steps= 819200 | ep_reward=-1.41 | succ=0.40 | len=698 timeout=0.58 | policy=-0.0007 value=0.0349 ent_c=5.3665 ent_d=0.0040 | kl=0.0044 clip=0.04 ev=0.69
[   90] stage=5 steps= 921600 | ep_reward=-1.28 | succ=0.40 | len=733 timeout=0.45 | policy=-0.0003 value=0.0417 ent_c=5.3074 ent_d=0.0055 | kl=0.0051 clip=0.06 ev=0.61
[  100] stage=5 steps=1024000 | ep_reward=-0.27 | succ=0.46 | len=525 timeout=0.38 | policy=-0.0018 value=0.0883 ent_c=5.2729 ent_d=0.0053 | kl=0.0051 clip=0.05 ev=0.49
[  110] stage=5 steps=1126400 | ep_reward=-0.83 | succ=0.44 | len=697 timeout=0.64 | policy=-0.0022 value=0.0624 ent_c=5.2788 ent_d=0.0051 | kl=0.0050 clip=0.04 ev=0.55
[  120] stage=5 steps=1228800 | ep_reward=-2.19 | succ=0.38 | len=760 timeout=0.55 | policy=-0.0011 value=0.0474 ent_c=5.2808 ent_d=0.0045 | kl=0.0049 clip=0.04 ev=0.54
[  130] stage=5 steps=1331200 | ep_reward=-1.38 | succ=0.40 | len=799 timeout=0.70 | policy=-0.0015 value=0.0415 ent_c=5.2944 ent_d=0.0034 | kl=0.0056 clip=0.06 ev=0.65
[  140] stage=5 steps=1433600 | ep_reward=0.16 | succ=0.56 | len=721 timeout=0.27 | policy=-0.0017 value=0.0757 ent_c=5.2561 ent_d=0.0042 | kl=0.0047 clip=0.04 ev=0.60
[  150] stage=5 steps=1536000 | ep_reward=-0.81 | succ=0.44 | len=724 timeout=0.62 | policy=-0.0015 value=0.0613 ent_c=5.2438 ent_d=0.0035 | kl=0.0044 clip=0.04 ev=0.65
[  160] stage=5 steps=1638400 | ep_reward=-1.76 | succ=0.44 | len=612 timeout=0.55 | policy=-0.0014 value=0.0867 ent_c=5.2564 ent_d=0.0042 | kl=0.0058 clip=0.06 ev=0.46
[  170] stage=5 steps=1740800 | ep_reward=0.03 | succ=0.38 | len=632 timeout=0.42 | policy=-0.0010 value=0.0636 ent_c=5.2617 ent_d=0.0054 | kl=0.0053 clip=0.06 ev=0.58
[  180] stage=5 steps=1843200 | ep_reward=-1.40 | succ=0.42 | len=827 timeout=0.64 | policy=-0.0027 value=0.0570 ent_c=5.2575 ent_d=0.0034 | kl=0.0065 clip=0.07 ev=0.58
[  190] stage=5 steps=1945600 | ep_reward=-0.49 | succ=0.46 | len=652 timeout=0.54 | policy=-0.0011 value=0.0513 ent_c=5.2446 ent_d=0.0061 | kl=0.0047 clip=0.05 ev=0.61
[  200] stage=5 steps=2048000 | ep_reward=-2.82 | succ=0.44 | len=701 timeout=0.69 | policy=-0.0025 value=0.0800 ent_c=5.2437 ent_d=0.0036 | kl=0.0049 clip=0.05 ev=0.36
  saved → results\run_03\model_200.pt
[  210] stage=5 steps=2150400 | ep_reward=-2.76 | succ=0.36 | len=771 timeout=0.60 | policy=-0.0033 value=0.0798 ent_c=5.2279 ent_d=0.0050 | kl=0.0062 clip=0.07 ev=0.42
[  220] stage=5 steps=2252800 | ep_reward=-1.37 | succ=0.58 | len=773 timeout=0.55 | policy=-0.0029 value=0.0618 ent_c=5.2057 ent_d=0.0064 | kl=0.0058 clip=0.06 ev=0.56
[  230] stage=5 steps=2355200 | ep_reward=0.03 | succ=0.50 | len=548 timeout=0.47 | policy=-0.0008 value=0.0626 ent_c=5.1768 ent_d=0.0055 | kl=0.0051 clip=0.06 ev=0.60
[  240] stage=5 steps=2457600 | ep_reward=-1.24 | succ=0.46 | len=638 timeout=0.54 | policy=-0.0025 value=0.0850 ent_c=5.1539 ent_d=0.0040 | kl=0.0070 clip=0.09 ev=0.40
[  250] stage=5 steps=2560000 | ep_reward=-1.51 | succ=0.42 | len=803 timeout=0.70 | policy=-0.0032 value=0.0448 ent_c=5.1791 ent_d=0.0033 | kl=0.0054 clip=0.07 ev=0.61
[  260] stage=5 steps=2662400 | ep_reward=-0.56 | succ=0.40 | len=641 timeout=0.58 | policy=-0.0029 value=0.0642 ent_c=5.1817 ent_d=0.0039 | kl=0.0061 clip=0.07 ev=0.50
[  270] stage=5 steps=2764800 | ep_reward=-1.23 | succ=0.38 | len=626 timeout=0.38 | policy=-0.0002 value=0.0807 ent_c=5.2002 ent_d=0.0092 | kl=0.0054 clip=0.05 ev=0.39
[  280] stage=5 steps=2867200 | ep_reward=-1.07 | succ=0.38 | len=669 timeout=0.64 | policy=-0.0025 value=0.0425 ent_c=5.1880 ent_d=0.0041 | kl=0.0062 clip=0.07 ev=0.55
[  290] stage=5 steps=2969600 | ep_reward=-2.69 | succ=0.44 | len=761 timeout=0.60 | policy=-0.0018 value=0.0356 ent_c=5.1631 ent_d=0.0040 | kl=0.0045 clip=0.04 ev=0.41
[  300] stage=5 steps=3072000 | ep_reward=-0.37 | succ=0.54 | len=631 timeout=0.46 | policy=-0.0037 value=0.0552 ent_c=5.1695 ent_d=0.0047 | kl=0.0070 clip=0.09 ev=0.51
[  310] stage=5 steps=3174400 | ep_reward=-0.32 | succ=0.52 | len=658 timeout=0.46 | policy=-0.0024 value=0.0720 ent_c=5.1794 ent_d=0.0045 | kl=0.0063 clip=0.08 ev=0.49
[  320] stage=5 steps=3276800 | ep_reward=-0.91 | succ=0.48 | len=684 timeout=0.42 | policy=-0.0007 value=0.0413 ent_c=5.1865 ent_d=0.0068 | kl=0.0035 clip=0.03 ev=0.57
[  330] stage=5 steps=3379200 | ep_reward=-0.20 | succ=0.52 | len=602 timeout=0.29 | policy=-0.0018 value=0.0421 ent_c=5.1846 ent_d=0.0077 | kl=0.0053 clip=0.05 ev=0.68
[  340] stage=5 steps=3481600 | ep_reward=-1.35 | succ=0.46 | len=748 timeout=0.45 | policy=-0.0022 value=0.0450 ent_c=5.1898 ent_d=0.0064 | kl=0.0061 clip=0.07 ev=0.55
[  350] stage=5 steps=3584000 | ep_reward=-2.25 | succ=0.36 | len=604 timeout=0.46 | policy=-0.0016 value=0.0923 ent_c=5.2128 ent_d=0.0059 | kl=0.0067 clip=0.08 ev=0.28
[  360] stage=5 steps=3686400 | ep_reward=0.01 | succ=0.50 | len=600 timeout=0.47 | policy=-0.0007 value=0.0695 ent_c=5.2318 ent_d=0.0050 | kl=0.0034 clip=0.02 ev=0.58
[  370] stage=5 steps=3788800 | ep_reward=-1.59 | succ=0.38 | len=658 timeout=0.60 | policy=-0.0022 value=0.0596 ent_c=5.2185 ent_d=0.0029 | kl=0.0050 clip=0.05 ev=0.43
[  380] stage=5 steps=3891200 | ep_reward=-0.61 | succ=0.46 | len=631 timeout=0.57 | policy=-0.0016 value=0.0522 ent_c=5.2088 ent_d=0.0037 | kl=0.0048 clip=0.04 ev=0.56
[  390] stage=5 steps=3993600 | ep_reward=-1.44 | succ=0.40 | len=734 timeout=0.70 | policy=-0.0021 value=0.0476 ent_c=5.2095 ent_d=0.0016 | kl=0.0036 clip=0.03 ev=0.57
[  400] stage=5 steps=4096000 | ep_reward=-1.83 | succ=0.46 | len=587 timeout=0.46 | policy=-0.0047 value=0.1320 ent_c=5.1738 ent_d=0.0033 | kl=0.0064 clip=0.07 ev=0.22
  saved → results\run_03\model_400.pt
[  410] stage=5 steps=4198400 | ep_reward=-0.70 | succ=0.54 | len=616 timeout=0.40 | policy=-0.0011 value=0.0957 ent_c=5.1723 ent_d=0.0033 | kl=0.0068 clip=0.08 ev=0.49
[  420] stage=5 steps=4300800 | ep_reward=-1.22 | succ=0.42 | len=721 timeout=0.55 | policy=-0.0016 value=0.0397 ent_c=5.1636 ent_d=0.0033 | kl=0.0062 clip=0.08 ev=0.56
[  430] stage=5 steps=4403200 | ep_reward=-0.74 | succ=0.46 | len=532 timeout=0.46 | policy=-0.0013 value=0.0864 ent_c=5.1422 ent_d=0.0038 | kl=0.0068 clip=0.07 ev=0.39
[  440] stage=5 steps=4505600 | ep_reward=-2.37 | succ=0.40 | len=812 timeout=0.67 | policy=-0.0015 value=0.0699 ent_c=5.1381 ent_d=0.0021 | kl=0.0064 clip=0.07 ev=0.43
[  450] stage=5 steps=4608000 | ep_reward=-0.43 | succ=0.42 | len=618 timeout=0.55 | policy=-0.0020 value=0.0590 ent_c=5.1376 ent_d=0.0036 | kl=0.0051 clip=0.05 ev=0.58
[  460] stage=5 steps=4710400 | ep_reward=0.13 | succ=0.54 | len=654 timeout=0.31 | policy=-0.0022 value=0.0800 ent_c=5.1162 ent_d=0.0035 | kl=0.0074 clip=0.10 ev=0.54
[  470] stage=5 steps=4812800 | ep_reward=-1.50 | succ=0.36 | len=809 timeout=0.64 | policy=-0.0020 value=0.0417 ent_c=5.0918 ent_d=0.0023 | kl=0.0059 clip=0.07 ev=0.58
[  480] stage=5 steps=4915200 | ep_reward=-1.94 | succ=0.40 | len=707 timeout=0.55 | policy=-0.0036 value=0.0609 ent_c=5.0925 ent_d=0.0035 | kl=0.0051 clip=0.05 ev=0.51
[  490] stage=5 steps=5017600 | ep_reward=-0.89 | succ=0.42 | len=644 timeout=0.46 | policy=-0.0020 value=0.0848 ent_c=5.1054 ent_d=0.0042 | kl=0.0062 clip=0.07 ev=0.45
[  500] stage=5 steps=5120000 | ep_reward=0.41 | succ=0.52 | len=691 timeout=0.33 | policy=-0.0018 value=0.0952 ent_c=5.0930 ent_d=0.0044 | kl=0.0047 clip=0.05 ev=0.54
[  510] stage=5 steps=5222400 | ep_reward=0.67 | succ=0.58 | len=507 timeout=0.35 | policy=-0.0025 value=0.1131 ent_c=5.0956 ent_d=0.0048 | kl=0.0042 clip=0.04 ev=0.59
[  520] stage=5 steps=5324800 | ep_reward=-0.85 | succ=0.36 | len=815 timeout=0.45 | policy=-0.0002 value=0.0763 ent_c=5.1026 ent_d=0.0034 | kl=0.0048 clip=0.05 ev=0.49
[  530] stage=5 steps=5427200 | ep_reward=-0.87 | succ=0.50 | len=590 timeout=0.54 | policy=-0.0000 value=0.0807 ent_c=5.0927 ent_d=0.0034 | kl=0.0051 clip=0.05 ev=0.38
[  540] stage=5 steps=5529600 | ep_reward=-1.60 | succ=0.42 | len=663 timeout=0.45 | policy=-0.0025 value=0.0653 ent_c=5.0813 ent_d=0.0034 | kl=0.0054 clip=0.06 ev=0.43
[  550] stage=5 steps=5632000 | ep_reward=-1.26 | succ=0.34 | len=688 timeout=0.70 | policy=-0.0022 value=0.0304 ent_c=5.0606 ent_d=0.0025 | kl=0.0056 clip=0.07 ev=0.60
[  560] stage=5 steps=5734400 | ep_reward=-0.36 | succ=0.50 | len=609 timeout=0.45 | policy=-0.0027 value=0.0551 ent_c=5.0752 ent_d=0.0034 | kl=0.0052 clip=0.06 ev=0.54
[  570] stage=5 steps=5836800 | ep_reward=-2.51 | succ=0.40 | len=850 timeout=0.89 | policy=-0.0020 value=0.0222 ent_c=5.0784 ent_d=0.0028 | kl=0.0052 clip=0.06 ev=0.63
[  580] stage=5 steps=5939200 | ep_reward=-1.42 | succ=0.36 | len=609 timeout=0.64 | policy=-0.0021 value=0.0621 ent_c=5.0836 ent_d=0.0043 | kl=0.0056 clip=0.07 ev=0.40
[  590] stage=5 steps=6041600 | ep_reward=-1.65 | succ=0.36 | len=775 timeout=0.73 | policy=-0.0031 value=0.0544 ent_c=5.0760 ent_d=0.0035 | kl=0.0035 clip=0.03 ev=0.42
[  600] stage=5 steps=6144000 | ep_reward=-0.14 | succ=0.46 | len=630 timeout=0.31 | policy=-0.0020 value=0.1059 ent_c=5.0617 ent_d=0.0034 | kl=0.0062 clip=0.07 ev=0.45
  saved → results\run_03\model_600.pt
[  610] stage=5 steps=6246400 | ep_reward=-1.73 | succ=0.36 | len=699 timeout=0.62 | policy=-0.0016 value=0.0518 ent_c=5.0403 ent_d=0.0046 | kl=0.0053 clip=0.06 ev=0.52
[  620] stage=5 steps=6348800 | ep_reward=-0.98 | succ=0.44 | len=636 timeout=0.62 | policy=-0.0024 value=0.0387 ent_c=5.0615 ent_d=0.0047 | kl=0.0046 clip=0.05 ev=0.59
[  630] stage=5 steps=6451200 | ep_reward=-0.45 | succ=0.44 | len=706 timeout=0.50 | policy=-0.0021 value=0.0757 ent_c=5.0419 ent_d=0.0032 | kl=0.0043 clip=0.03 ev=0.52
[  640] stage=5 steps=6553600 | ep_reward=-0.99 | succ=0.38 | len=676 timeout=0.58 | policy=-0.0025 value=0.0374 ent_c=5.0290 ent_d=0.0041 | kl=0.0047 clip=0.04 ev=0.64
[  650] stage=5 steps=6656000 | ep_reward=-2.42 | succ=0.40 | len=729 timeout=0.70 | policy=-0.0021 value=0.0537 ent_c=4.9870 ent_d=0.0021 | kl=0.0053 clip=0.05 ev=0.51
[  660] stage=5 steps=6758400 | ep_reward=1.34 | succ=0.62 | len=513 timeout=0.18 | policy=-0.0008 value=0.1229 ent_c=4.9753 ent_d=0.0048 | kl=0.0046 clip=0.05 ev=0.46
[  670] stage=5 steps=6860800 | ep_reward=-0.22 | succ=0.34 | len=637 timeout=0.42 | policy=-0.0023 value=0.0512 ent_c=4.9774 ent_d=0.0032 | kl=0.0054 clip=0.06 ev=0.62
[  680] stage=5 steps=6963200 | ep_reward=-1.09 | succ=0.38 | len=682 timeout=0.60 | policy=-0.0001 value=0.0395 ent_c=4.9530 ent_d=0.0021 | kl=0.0058 clip=0.07 ev=0.64
[  690] stage=5 steps=7065600 | ep_reward=-1.10 | succ=0.48 | len=743 timeout=0.55 | policy=-0.0035 value=0.0516 ent_c=4.9718 ent_d=0.0028 | kl=0.0059 clip=0.06 ev=0.49
[  700] stage=5 steps=7168000 | ep_reward=-1.62 | succ=0.36 | len=695 timeout=0.69 | policy=-0.0016 value=0.0287 ent_c=4.9603 ent_d=0.0043 | kl=0.0061 clip=0.07 ev=0.62
[  710] stage=5 steps=7270400 | ep_reward=-1.76 | succ=0.54 | len=634 timeout=0.54 | policy=-0.0021 value=0.0850 ent_c=4.9495 ent_d=0.0032 | kl=0.0043 clip=0.04 ev=0.40
[  720] stage=5 steps=7372800 | ep_reward=-0.75 | succ=0.46 | len=581 timeout=0.54 | policy=-0.0016 value=0.0344 ent_c=4.9634 ent_d=0.0034 | kl=0.0061 clip=0.07 ev=0.62
[  730] stage=5 steps=7475200 | ep_reward=-2.34 | succ=0.26 | len=846 timeout=0.70 | policy=-0.0029 value=0.0187 ent_c=4.9480 ent_d=0.0021 | kl=0.0062 clip=0.07 ev=0.66
[  740] stage=5 steps=7577600 | ep_reward=-2.43 | succ=0.42 | len=881 timeout=0.70 | policy=-0.0028 value=0.0258 ent_c=4.9473 ent_d=0.0023 | kl=0.0052 clip=0.05 ev=0.49
[  750] stage=5 steps=7680000 | ep_reward=-1.11 | succ=0.36 | len=615 timeout=0.50 | policy=-0.0027 value=0.0716 ent_c=4.9461 ent_d=0.0039 | kl=0.0059 clip=0.05 ev=0.37
[  760] stage=5 steps=7782400 | ep_reward=-3.61 | succ=0.28 | len=938 timeout=1.00 | policy=-0.0026 value=0.0078 ent_c=4.9493 ent_d=0.0023 | kl=0.0069 clip=0.08 ev=0.75
[  770] stage=5 steps=7884800 | ep_reward=-0.64 | succ=0.42 | len=565 timeout=0.36 | policy=-0.0030 value=0.0752 ent_c=4.9550 ent_d=0.0038 | kl=0.0053 clip=0.06 ev=0.48
[  780] stage=5 steps=7987200 | ep_reward=-2.18 | succ=0.46 | len=806 timeout=0.67 | policy=-0.0030 value=0.0272 ent_c=4.9655 ent_d=0.0030 | kl=0.0072 clip=0.08 ev=0.57
[  790] stage=5 steps=8089600 | ep_reward=-2.06 | succ=0.42 | len=716 timeout=0.58 | policy=-0.0019 value=0.0596 ent_c=4.9799 ent_d=0.0042 | kl=0.0051 clip=0.05 ev=0.32
[  800] stage=5 steps=8192000 | ep_reward=-3.01 | succ=0.42 | len=911 timeout=0.90 | policy=-0.0013 value=0.0129 ent_c=4.9847 ent_d=0.0016 | kl=0.0077 clip=0.10 ev=0.57
  saved → results\run_03\model_800.pt
[  810] stage=5 steps=8294400 | ep_reward=-1.38 | succ=0.36 | len=757 timeout=0.64 | policy=-0.0026 value=0.0380 ent_c=4.9681 ent_d=0.0027 | kl=0.0050 clip=0.06 ev=0.56
[  820] stage=5 steps=8396800 | ep_reward=-1.30 | succ=0.46 | len=701 timeout=0.50 | policy=-0.0020 value=0.0365 ent_c=4.9798 ent_d=0.0024 | kl=0.0052 clip=0.06 ev=0.57
[  830] stage=5 steps=8499200 | ep_reward=-3.38 | succ=0.40 | len=910 timeout=0.89 | policy=-0.0021 value=0.0123 ent_c=4.9903 ent_d=0.0016 | kl=0.0040 clip=0.04 ev=0.68
[  840] stage=5 steps=8601600 | ep_reward=-1.79 | succ=0.42 | len=594 timeout=0.67 | policy=-0.0017 value=0.0488 ent_c=4.9790 ent_d=0.0033 | kl=0.0050 clip=0.04 ev=0.55
[  850] stage=5 steps=8704000 | ep_reward=-1.57 | succ=0.52 | len=788 timeout=0.55 | policy=-0.0010 value=0.0229 ent_c=4.9715 ent_d=0.0025 | kl=0.0060 clip=0.07 ev=0.76
[  860] stage=5 steps=8806400 | ep_reward=-1.44 | succ=0.48 | len=753 timeout=0.58 | policy=0.0002 value=0.0457 ent_c=4.9988 ent_d=0.0022 | kl=0.0064 clip=0.07 ev=0.62
[  870] stage=5 steps=8908800 | ep_reward=-2.14 | succ=0.44 | len=782 timeout=0.70 | policy=-0.0008 value=0.0280 ent_c=5.0109 ent_d=0.0029 | kl=0.0071 clip=0.07 ev=0.58
[  880] stage=5 steps=9011200 | ep_reward=-1.31 | succ=0.40 | len=610 timeout=0.50 | policy=-0.0029 value=0.0715 ent_c=4.9833 ent_d=0.0022 | kl=0.0075 clip=0.09 ev=0.37
[  890] stage=5 steps=9113600 | ep_reward=-1.94 | succ=0.46 | len=760 timeout=0.73 | policy=-0.0021 value=0.0309 ent_c=4.9524 ent_d=0.0021 | kl=0.0050 clip=0.05 ev=0.56
[  900] stage=5 steps=9216000 | ep_reward=-2.44 | succ=0.34 | len=778 timeout=0.64 | policy=-0.0031 value=0.0418 ent_c=4.9634 ent_d=0.0024 | kl=0.0065 clip=0.08 ev=0.44
[  910] stage=5 steps=9318400 | ep_reward=-2.38 | succ=0.34 | len=885 timeout=0.78 | policy=-0.0031 value=0.0333 ent_c=4.9702 ent_d=0.0013 | kl=0.0075 clip=0.09 ev=0.64
[  920] stage=5 steps=9420800 | ep_reward=-0.87 | succ=0.44 | len=615 timeout=0.50 | policy=-0.0011 value=0.0609 ent_c=4.9638 ent_d=0.0045 | kl=0.0052 clip=0.05 ev=0.57
[  930] stage=5 steps=9523200 | ep_reward=0.30 | succ=0.58 | len=568 timeout=0.23 | policy=-0.0008 value=0.0665 ent_c=4.9816 ent_d=0.0040 | kl=0.0063 clip=0.07 ev=0.68
[  940] stage=5 steps=9625600 | ep_reward=-2.89 | succ=0.52 | len=738 timeout=0.82 | policy=-0.0036 value=0.0291 ent_c=4.9910 ent_d=0.0021 | kl=0.0064 clip=0.06 ev=0.42
[  950] stage=5 steps=9728000 | ep_reward=-0.05 | succ=0.46 | len=596 timeout=0.42 | policy=-0.0014 value=0.0485 ent_c=4.9945 ent_d=0.0027 | kl=0.0079 clip=0.10 ev=0.67
[  960] stage=5 steps=9830400 | ep_reward=-0.60 | succ=0.42 | len=685 timeout=0.54 | policy=-0.0023 value=0.0570 ent_c=4.9777 ent_d=0.0032 | kl=0.0047 clip=0.05 ev=0.52
[  970] stage=5 steps=9932800 | ep_reward=-1.95 | succ=0.42 | len=768 timeout=0.73 | policy=-0.0020 value=0.0266 ent_c=4.9635 ent_d=0.0029 | kl=0.0070 clip=0.08 ev=0.66
[  980] stage=5 steps=10035200 | ep_reward=-1.53 | succ=0.48 | len=805 timeout=0.50 | policy=-0.0025 value=0.0320 ent_c=4.9232 ent_d=0.0025 | kl=0.0062 clip=0.07 ev=0.65
[  990] stage=5 steps=10137600 | ep_reward=-0.83 | succ=0.40 | len=684 timeout=0.62 | policy=-0.0027 value=0.0432 ent_c=4.8974 ent_d=0.0032 | kl=0.0037 clip=0.04 ev=0.65
[ 1000] stage=5 steps=10240000 | ep_reward=-0.81 | succ=0.50 | len=663 timeout=0.45 | policy=-0.0018 value=0.0324 ent_c=4.8843 ent_d=0.0035 | kl=0.0063 clip=0.08 ev=0.71
  saved → results\run_03\model_1000.pt
[ 1010] stage=5 steps=10342400 | ep_reward=-1.15 | succ=0.50 | len=630 timeout=0.54 | policy=-0.0010 value=0.0503 ent_c=4.8602 ent_d=0.0033 | kl=0.0053 clip=0.05 ev=0.60
[ 1020] stage=5 steps=10444800 | ep_reward=-3.18 | succ=0.36 | len=897 timeout=0.89 | policy=-0.0020 value=0.0136 ent_c=4.8567 ent_d=0.0013 | kl=0.0055 clip=0.06 ev=0.71
[ 1030] stage=5 steps=10547200 | ep_reward=-1.78 | succ=0.38 | len=640 timeout=0.38 | policy=-0.0030 value=0.0900 ent_c=4.8979 ent_d=0.0037 | kl=0.0083 clip=0.10 ev=0.31
[ 1040] stage=5 steps=10649600 | ep_reward=-1.51 | succ=0.42 | len=752 timeout=0.67 | policy=-0.0027 value=0.0460 ent_c=4.8658 ent_d=0.0027 | kl=0.0062 clip=0.08 ev=0.65
[ 1050] stage=5 steps=10752000 | ep_reward=-2.27 | succ=0.52 | len=747 timeout=0.55 | policy=-0.0008 value=0.0622 ent_c=4.8612 ent_d=0.0040 | kl=0.0059 clip=0.06 ev=0.35
[ 1060] stage=5 steps=10854400 | ep_reward=-2.86 | succ=0.38 | len=858 timeout=0.89 | policy=-0.0025 value=0.0164 ent_c=4.8557 ent_d=0.0017 | kl=0.0049 clip=0.05 ev=0.62
[ 1070] stage=5 steps=10956800 | ep_reward=-2.25 | succ=0.50 | len=704 timeout=0.40 | policy=-0.0037 value=0.0707 ent_c=4.8434 ent_d=0.0027 | kl=0.0055 clip=0.05 ev=0.40
[ 1080] stage=5 steps=11059200 | ep_reward=-0.74 | succ=0.46 | len=619 timeout=0.44 | policy=-0.0030 value=0.0899 ent_c=4.8260 ent_d=0.0041 | kl=0.0072 clip=0.08 ev=0.51
[ 1090] stage=5 steps=11161600 | ep_reward=0.38 | succ=0.50 | len=510 timeout=0.25 | policy=-0.0027 value=0.1150 ent_c=4.8062 ent_d=0.0032 | kl=0.0058 clip=0.06 ev=0.49
[ 1100] stage=5 steps=11264000 | ep_reward=-1.30 | succ=0.32 | len=707 timeout=0.73 | policy=-0.0025 value=0.0392 ent_c=4.8063 ent_d=0.0021 | kl=0.0061 clip=0.07 ev=0.56
[ 1110] stage=5 steps=11366400 | ep_reward=-1.39 | succ=0.44 | len=690 timeout=0.54 | policy=-0.0029 value=0.0621 ent_c=4.8172 ent_d=0.0031 | kl=0.0084 clip=0.11 ev=0.57
[ 1120] stage=5 steps=11468800 | ep_reward=-2.89 | succ=0.54 | len=890 timeout=0.67 | policy=-0.0027 value=0.0307 ent_c=4.8114 ent_d=0.0019 | kl=0.0068 clip=0.08 ev=0.52
[ 1130] stage=5 steps=11571200 | ep_reward=-0.27 | succ=0.54 | len=579 timeout=0.40 | policy=-0.0029 value=0.0544 ent_c=4.7917 ent_d=0.0051 | kl=0.0065 clip=0.08 ev=0.63
```