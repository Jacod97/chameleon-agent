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
