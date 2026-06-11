<!-- 🖼️ 표시가 붙은 인용 블록은 PPT 제작용 이미지 제안 메모입니다. 보고서 제출 전 삭제하세요. -->

# Chameleon Agent: 강화학습 기반 실내 모기 포획 로봇 시뮬레이션

## 1. Overview

### 1.1 배경

- 모기로 인한 일상적 불편: 수면 중 소음, 흡혈
- 기존 퇴치 방식의 한계
  - 스프레이·모기향: 화학물질 사용에 따른 부작용
  - 물리적 포획: 자동화 어려움
- 본 프로젝트: Unity 가상환경에서 모기를 자율 포획하는 강화학습 에이전트 개발
- 최종 목표: 가상환경에서 검증한 정책을 실제 로봇 시스템으로 이식

> 🖼️ **PPT 이미지 제안** — 도입 슬라이드: 모기로 인한 불편을 표현한 일러스트 + 혀로 벌레를 잡는 실제 카멜레온 사진. 프로젝트 컨셉이 한눈에 전달됨.

### 1.2 목표

1. 집안의 모든 모기 포획 (최우선 목표)
2. 포획 과정에서 집안 물품 파손 금지
3. 현실과 동일한 물리 조건 전제
   - 실물 로봇 이식 고려
   - 게임적 단순화 배제

## 2. Environment

### 2.1 가상 공간 구조

- 규모: 가로 7m × 세로 7m × 높이 3m 고정 원룸
- 구성: 벽·바닥·천장으로 둘러싸인 밀폐 공간, 가구 고정 배치
- 방 구조는 매 에피소드 동일
- Unity 물리 엔진 기반: 중력·충돌 등 현실과 동일한 물리 적용
- 동일한 방 4개 복제 → 에이전트 4개가 병렬로 경험 수집

> 🖼️ **PPT 이미지 제안** — Unity 씬 스크린샷 2장: ① 방 전체 부감 샷, ② 병렬 영역 4개가 나란히 보이는 샷.

### 2.2 카멜레온 에이전트

- 약 30cm 소형 홈 로봇으로, 바퀴 구동 차체(전·후진, 제자리 회전) 위에 독립적으로 좌우·상하 회전하는 머리를 얹은 구조이며, 매 에피소드 방 중앙에서 시작함
- 카메라와 혀 발사구가 모두 머리에 장착되어 있어, 머리를 돌려 모기를 찾고 조준한 방향으로 발사하는 행동이 구조적으로 요구됨
- 시야는 시야각 약 90도, 유효 거리 약 3m이며, 가구나 벽에 가려진 모기는 감지하지 못함
- 약 5mm 크기의 모기는 영상 인식으로 안정적 검출이 어려우므로, 시야·차폐 판정을 통과한 모기의 상대 위치와 속도를 센서로 직접 수신함
- 공격은 사거리 약 2.5m의 늘어나는 혀로 수행하며, 발사·복귀 사이클 0.3초가 곧 쿨다운이고 혀 끝 흡착력으로 대상을 부착해 끌어옴

```mermaid
flowchart LR
    M["모기"] --> D{"거리 3m 이내"}
    D -->|예| F{"시야각 90도 이내"}
    F -->|예| O{"가구·벽 차폐 없음"}
    O -->|예| IN["관측 집합에 포함"]
    D -->|아니오| X["감지 안 됨"]
    F -->|아니오| X
    O -->|아니오| X
```

```mermaid
stateDiagram-v2
    [*] --> 대기
    대기 --> 발사 : 발사 명령 — 명중 판정·보상 즉시 확정
    발사 --> 복귀 : 0.15초
    복귀 --> 대기 : 사이클 종료 (총 0.3초)
```

> 🖼️ **PPT 이미지 제안** — 에이전트 클로즈업 스크린샷에 부위 라벨(바퀴·몸통·머리·발사구) + 혀 발사 순간 인게임 GIF.

### 2.3 가구

- 고정된 수·위치로 배치, 가구별 현실적 무게와 파손 임계값 부여
- 혀 흡착 시 결과는 물리 엔진과 무게가 자동 결정
  - 모기 (거의 무중력): 즉시 빨려옴 → 포획
  - 가벼운 물체 (식기·책 등): 끌려오다 바닥에 떨어지며 충돌
  - 무거운 가구 (책상·냉장고 등): 움직이지 않음
- 충돌 충격이 파손 임계값 초과 시 파손 → 에피소드 즉시 실패 종료

### 2.4 모기

- 에피소드당 3~10마리 무작위 생성, 초기 위치는 방 안 임의 공중
- 행동 패턴: 무작위 비행 ↔ 벽·천장·가구 착지 반복
- 카멜레온을 인식하지 않음 (회피 행동 없음), 개체 간 상호작용 없음
- 현실 모기 수준의 특성: 크기 약 5mm, 비행 속도 약 초속 1m

## 3. MDP

- 모기 포획 문제를 마르코프 결정 과정으로 정의
- 상태 전이: Unity 물리 엔진이 담당 (에이전트는 전이 모델을 모르는 채 경험으로 학습)
- 시야·차폐 제약으로 부분 관측만 수신 → 엄밀하게는 부분 관측 마르코프 결정 과정

```mermaid
flowchart LR
    AG["에이전트<br/>(카멜레온)"] -->|"행동: 이동 · 차체 회전<br/>머리 회전 · 혀 발사"| ENV["환경<br/>(방 · 가구 · 모기)"]
    ENV -->|"관측: 자기 상태 벡터<br/>+ 시야 안 모기 집합"| AG
    ENV -->|"보상: 포획 + / 파손 − 등"| AG
```

### 3.1 관측 공간

**자기 상태 벡터 (10차원)**

| 항목 | 차원 | 설명 |
|------|------|------|
| 위치 | 2 | 시작 지점 기준 상대 좌표 (바닥 주행이므로 높이 생략) |
| 속도 | 2 | 차체 방향 기준 좌표계 |
| 머리 각도 | 2 | 상하·좌우 조준 각도 |
| 남은 모기 수 | 1 | 방 전체 잔여 수 (시야와 무관) |
| 혀 준비 상태 | 1 | 발사 가능 1, 사이클 진행 중 0 |
| 무실수 여부 | 1 | 헛발사가 한 번도 없으면 1 |
| 최근 발사 횟수 | 1 | 직전 포획 이후 발사 횟수 (3회에서 포화) |

- 뒤의 세 항목은 보상 구조를 가치 함수가 예측 가능하게 만들기 위한 관측
  - 예: 혀 사이클 중 발사 입력이 무시되는 사실을 모르면, 같은 행동이 다른 결과를 내는 것처럼 보여 학습 방해
- 차체의 절대 방향은 관측에서 제외
  - 모기 위치가 머리 기준 상대 좌표 → 조준·접근 정보가 이미 충분
  - 절대 각도 제외 시 같은 상대 상황이 차체 방향과 무관하게 같은 관측 → 일반화 유리

**모기 집합 관측**

- 시야·차폐 판정을 통과한 모기들의 집합 (0~최대 10마리, 매 스텝 가변)
- 모기 한 마리당 6개 값: 머리 기준 상대 위치 3개 + 상대 속도 3개
- 가변 크기 집합은 신경망의 PointNet 인코더가 고정 크기 특징으로 변환

### 3.2 행동 공간

**연속 행동 (4개, 각각 −1 ~ 1)**

| 항목 | 설명 |
|------|------|
| 전진·후진 | 최대 전진 초속 0.5m, 후진 초속 0.3m |
| 차체 회전 | 최대 초당 120도, 제자리 회전 가능 |
| 머리 좌우 회전 | 최대 초당 180도, 좌우 90도 제한 |
| 머리 상하 회전 | 최대 초당 120도, 아래 60도 ~ 위 45도 제한 |

**이산 행동 (1개)**

- 대기 또는 혀 발사 중 선택
- 혀 사이클 진행 중의 발사 선택은 환경이 무시

### 3.3 보상 함수

| 항목 | 조건 | 값 |
|------|------|----|
| 모기 포획 | 혀가 모기에 명중 (마리당) | +1.0 |
| 허공 발사 | 발사했으나 빗나감 | −0.01 |
| 시간 경과 | 매 물리 스텝 | −0.001 |
| 거리 접근 | 시야 안 최근접 모기와의 거리 감소 | 1m당 +0.05 |
| 가구 파손 | 파손 발생 (즉시 실패 종료) | −5.0 |
| 완전 포획 | 방 안 모든 모기 포획 (즉시 성공 종료) | +1.0 |
| 정밀 사격 | 헛발사 없이 완전 포획 달성 시 추가 | +2.0 |
| 효율 사격 | 직전 포획 이후 3발 이내 포획 시 추가 | +0.5 |

- 거리 접근 보상: 희소 보상 완화용 보상 형성 — 초기 학습에서 접근 행동을 먼저 유도
- 포획·허공 발사 판정은 발사 순간 즉시 확정
  - 사이클 종료 시점(0.3초 뒤) 판정 시 보상이 엉뚱한 후속 행동에 귀속 → 인과 학습 실패
- 정밀·효율 보너스: 무분별한 연사 대신 조준 후 발사 유도
  - 사격 경제성을 벌점이 아닌 보너스로 설계 — 실험에서 확인된 발사 기피 현상 때문 (5장 참조)

### 3.4 에피소드 종료 조건

| 조건 | 결과 |
|------|------|
| 모든 모기 포획 | 성공 종료, 완전 포획 보너스 지급 |
| 가구 파손 | 실패 종료, 파손 벌점 부여 |
| 최대 스텝 도달 | 중립 종료 — 마지막 상태의 가치 추정으로 이어서 계산 |

- 할인율 0.995 사용
  - 에피소드가 600~900 결정 스텝 → 통상적인 0.99로는 탐색 구간 보상 신호가 소실

## 4. RL Algorithm

### 4.1 PPO

본 프로젝트의 요구 조건 세 가지가 PPO 채택의 직접적인 근거이다.

- **요구 1 — 가구 파손 금지: 정책이 한 번에 급변하면 안 됨**
  - 파손은 즉시 실패 종료라, 정책이 한 번의 업데이트로 과격해지면 에피소드가 줄줄이 조기 종료되어 학습 데이터 자체가 망가짐
  - PPO 는 새 정책과 수집 시점 정책의 확률 비율이 일정 범위(본 프로젝트는 ±20%)를 벗어나면 학습을 차단 → 정책이 항상 점진적으로만 변해, 학습 내내 행동이 안전한 범위에 머묾

$$L^{\text{CLIP}}(\theta) = \hat{\mathbb{E}}_t \left[ \min \left( r_t(\theta)\hat{A}_t,\ \text{clip}(r_t(\theta), 1-\epsilon, 1+\epsilon)\hat{A}_t \right) \right], \qquad r_t(\theta) = \frac{\pi_\theta(a_t \mid s_t)}{\pi_{\theta_{\text{old}}}(a_t \mid s_t)}$$

- **요구 2 — 혼합 행동 공간: 연속 4개와 이산 1개를 한 정책으로**
  - 가치 기반 방법(DQN 계열)은 연속 행동을 다루지 못하고, 연속 전용 방법은 발사 같은 이산 선택의 결합이 부자연스러움
  - PPO 는 정책이 확률 분포를 직접 출력하는 구조라, 이동·회전(정규분포)과 발사(범주형 분포)의 로그 확률을 합산해 하나의 정책으로 묶고 동일한 클리핑 아래에서 함께 갱신 가능
- **요구 3 — 커리큘럼 학습: 환경 난이도가 도중에 바뀜**
  - 단계가 오르면 모기 수·속도가 달라져 과거 경험이 더 이상 현재 환경을 대표하지 못함
  - PPO 는 현재 정책으로 방금 모은 데이터만 쓰고 버리는 on-policy 방식 → 리플레이 버퍼에 옛 단계의 경험이 남아 학습을 오염시키는 문제가 구조적으로 없음
- on-policy 의 대가인 낮은 데이터 효율은 본 프로젝트에서는 문제가 아님
  - 시뮬레이션 20배 가속 + 방 4개 병렬 수집으로 데이터 수집 비용이 저렴
- 부수 이득 — 진단 가능성
  - PPO 가 제공하는 업데이트 건강 지표(정책 변화량, 클리핑 발동 비율)가 학습 내내 안정적이었기 때문에, 학습 정체가 발생할 때마다 원인을 알고리즘이 아닌 보상 설계로 좁혀 진단할 수 있었음 (5장의 문제 해결 과정이 그 결과)
- 이점 추정은 GAE 사용 — 크리틱의 가치 추정으로 보상 신호의 분산을 줄임
  - 본 프로젝트는 에피소드가 600~900 결정 스텝으로 길어 실제 누적 보상의 분산이 큼 → 가중치 0.95로 크리틱 추정과 절충

$$\hat{A}_t = \sum_{l=0}^{\infty}(\gamma\lambda)^l \delta_{t+l}, \qquad \delta_t = r_t + \gamma V(s_{t+1}) - V(s_t)$$

- 구현: 표준 트레이너 대신 PyTorch 직접 구현
  - 근거: 혼합 분포 설계, 엔트로피 분리 관리, 원시 행동 값 저장 등 본 프로젝트에 필요한 세부 제어가 표준 도구로는 불가

### 4.2 상호작용과 업데이트 구조

- 전체 시스템은 환경, 인코더, 액터, 크리틱, 버퍼 다섯 요소로 구성
- 실선 = 매 스텝 반복되는 상호작용, 점선 = 버퍼가 가득 찼을 때 일어나는 업데이트

```mermaid
flowchart LR
    ENV["환경<br/>(방 · 가구 · 모기)"]
    ENC["인코더<br/>자기 상태 MLP + 모기 집합 PointNet"]
    ACT["액터<br/>(정책: 연속 행동 + 발사 여부)"]
    CRI["크리틱<br/>(상태 가치)"]
    BUF["버퍼<br/>(약 1만 스텝)"]

    ENV -->|"관측"| ENC
    ENC -->|"공통 특징"| ACT
    ENC -->|"공통 특징"| CRI
    ACT -->|"행동"| ENV
    ACT -->|"행동 · 선택 확률 기록"| BUF
    ENV -->|"관측 · 보상 기록"| BUF
    CRI -->|"가치 추정 기록"| BUF
    BUF -.->|"이점 계산 → 정책 갱신"| ACT
    BUF -.->|"가치 목표 → 가치 갱신"| CRI
    BUF -.->|"두 손실의 기울기 역전파"| ENC
```

![상호작용과 업데이트 구조](docs/figures/interaction_update.png)

| 기호 | 의미 |
|------|------|
| $s_t$ | 시점 $t$ 의 관측 — 자기 상태 벡터 10차원 + 시야 안 모기 집합 |
| $z_t$ | 인코더가 두 관측을 결합해 만든 공통 특징 벡터 |
| $a_t$ | 행동 — 연속 4개(이동·차체 회전·머리 회전)와 발사 여부 |
| $r_t$ | 행동 $a_t$ 에 대해 환경이 준 보상 |
| $\log \pi_{\theta_{\text{old}}}(a_t \mid s_t)$ | 수집 시점 정책이 행동 $a_t$ 에 부여한 로그 확률 — PPO 비율의 분모로 사용 |
| $V(s_t)$ | 크리틱의 상태 가치 추정 — 이점 계산의 기준선 |
| $\hat{A}_t$ | 이점 — 행동이 평균 대비 얼마나 좋았는지의 GAE 추정치 |
| $L^{\text{CLIP}}$ | PPO 클리핑 목적 함수 — 정책(액터) 갱신에 사용 |
| $V_t^{\text{target}}$ | 가치 학습 목표 ($\hat{A}_t + V(s_t)$) — 크리틱 갱신에 사용 |
| $\nabla_\theta L$ | 정책 손실과 가치 손실을 합친 전체 손실의 기울기 — 인코더까지 역전파 |

- 상호작용 (실선): 환경의 관측을 인코더가 하나의 특징으로 압축 → 액터가 행동 선택 → 환경이 한 스텝 진행 → 그 결과(관측·행동·보상·가치 추정)를 버퍼에 기록
- 업데이트 (점선): 버퍼가 약 1만 스텝 차면 이점을 계산하고, 전체를 3회 순회하며 미니배치 단위로 액터·크리틱·인코더를 함께 갱신 → 버퍼 비우고 수집 재개
  - 이점은 병렬 에이전트별로 독립 계산 (서로 다른 에이전트의 시간 축이 섞이는 오염 방지)
- 구성 요소 세부
  - 인코더: 자기 상태 벡터는 MLP, 모기 집합은 PointNet(모기마다 공유 신경망 적용 후 최댓값 풀링 — 마릿수가 변해도 출력 크기 일정)으로 처리 후 결합
  - 액터: 연속 행동은 정규분포 표본에 쌍곡탄젠트로 범위 제한, 발사 여부는 범주형 분포
  - 버퍼: 범위 제한 전의 원시 행동 값을 저장 → 업데이트 시 역연산 없이 확률을 정확히 재계산 (경계 부근 수치 오차 차단)
- 안정화 장치: 탐색 분포의 표준편차 상한 (노이즈 폭주 방지), 연속·발사 행동의 엔트로피 분리 관리 (연속 쪽이 발사 쪽 탐색 신호를 압도하는 문제 방지)
- 학습 지표는 MLflow로 기록 — 손실·정책 변화량·가치 예측 정확도 외에 발사 엔트로피와 발사 시도율을 추적해 발사 정책 이상(난사·발사 기피)의 조기 경보로 활용 (5장 참조)

### 4.3 커리큘럼 학습

- 처음부터 최종 난이도로 학습 시 성공 경험이 희소 → 학습 불가
- 쉬운 조건에서 접근·조준을 먼저 익히고 단계적으로 난이도 상승

```mermaid
flowchart LR
    S1["1단계<br/>정지 1마리<br/>에이전트 근접"] --> S2["2단계<br/>정지 1마리<br/>방 전체"] --> S3["3단계<br/>저속 비행<br/>1마리"] --> S4["4단계<br/>정상 비행<br/>1마리"] --> S5["5단계<br/>정상 비행<br/>3마리"] --> S6["6단계<br/>정상 비행<br/>3~10마리"]
```

- 승급 기준: 포획률 (에피소드에 생성된 모기 중 잡은 비율)
  - 최근 50개 에피소드 평균 포획률 80% 초과 시 자동 승급
  - 전멸 여부를 기준으로 하지 않는 근거: 전멸 난이도는 모기 수에 대해 거듭제곱으로 증가 → 다마리 단계에서 커리큘럼 영구 정체
- 난이도 변수(모기 수·속도·생성 범위)는 학습 프로세스가 통신 채널로 주입, 환경은 에피소드 시작 시 적용

## 5. Experiment

### 5.1 실험 설정

- 화면 출력 없는 빌드 환경, 시뮬레이션 시간 20배 가속
- 동일한 방 4개에서 에이전트 4개 병렬 경험 수집
- 학습 지표는 MLflow 기록, 보상 수치·하이퍼파라미터는 실험을 거치며 조정 (본문 값은 현재 설정)

### 5.2 학습 경과와 문제 해결 과정

- 학습은 한 번에 완성되지 않음 — 정체 원인 진단과 수정을 반복
- 주요 사례 3가지:

```mermaid
flowchart TB
    subgraph CASE1["사례 1 — 보상 귀속 시점"]
        direction LR
        A1["포획 보상이 발사<br/>0.3초 뒤에 지급"] --> A2["보상이 엉뚱한 후속<br/>행동에 귀속"] --> A3["수정: 발사 순간<br/>즉시 판정·지급"] --> A4["포획률 0.24 → 0.66<br/>첫 커리큘럼 승급"]
    end
    subgraph CASE2["사례 2 — 발사 정책 진단"]
        direction LR
        B1["3단계 포획률 정체<br/>발사 엔트로피 0 붕괴"] --> B2["난사인지 기피인지<br/>구분 불가"] --> B3["발사 시도율<br/>지표 추가"] --> B4["에피소드당 발사 1~2회<br/>= 발사 기피로 판명"]
    end
    subgraph CASE3["사례 3 — 발사 기피 교정"]
        direction LR
        C1["엔트로피 계수 5배<br/>→ 붕괴 지연뿐, 실패"] --> C2["원인: 헛발사 벌점의<br/>즉각적 음수 신호"] --> C3["수정: 벌점 인하<br/>+ 효율 보너스로 역할 분리"] --> C4["검증 진행 중"]
    end
    CASE1 --> CASE2 --> CASE3
```

**사례 1 — 보상 귀속 시점 문제**

- 초기 구현: 포획 판정·보상이 혀 사이클 종료 시점(발사 0.3초 뒤)에 지급
- 그 사이 추가 행동이 여러 번 발생 → 보상이 원인 행동("조준하고 발사")이 아닌 후속 행동에 귀속
- 결과: 정책이 접근 보상만 모으고 발사하지 않는 방향으로 수렴
- 수정: 판정·보상을 발사 순간 즉시 확정
- 효과: 1단계 포획률 0.24 → 0.66, 최초의 커리큘럼 승급 발생

**사례 2 — 발사 정책 진단 도구**

- 3단계(움직이는 모기)에서 포획률 0.5 부근 정체 + 발사 엔트로피가 거의 0으로 붕괴
- 정책이 결정론적으로 굳었다는 신호 — 단, "무조건 쏨"인지 "거의 안 쏨"인지 엔트로피만으로 구분 불가
- 수집 데이터에서 발사 시도 비율을 집계하는 지표 추가
- 측정 결과: 에피소드당 발사 1~2회 → 발사 기피 상태로 확정

**사례 3 — 발사 기피와 보상 구조 수정**

- 발사 기피는 자기강화적
  - 발사 안 함 → 포획 경험 없음 → 발사의 이득 학습 불가 → 발사 더 감소
- 시도 1: 발사 행동의 엔트로피 계수 5배 → 붕괴를 약간 늦출 뿐 실패
- 진단: 두 차례 실험의 증거가 헛발사 벌점의 즉각적 음수 신호를 원인으로 지목
- 시도 2: 헛발사 벌점을 시도 비용이 거의 없는 수준으로 인하, 사격 경제성은 효율 보너스(양수)가 전담
  - 시도가 거의 공짜 → 발사 경험 풍부화
  - 적은 발수로 잡을수록 보너스 → 조준의 질은 계속 보상
- 현재 이 구조의 효과를 검증 중

> 🖼️ **PPT 이미지 제안** — MLflow 학습 곡선 캡처: 포획률·에피소드 보상·발사 엔트로피·발사 시도율 4개. 특히 발사 엔트로피와 발사 시도율이 함께 0으로 떨어지는 구간을 강조하면 사례 2의 진단 과정이 설득력 있게 전달됨.

### 5.3 현재 상태

- 커리큘럼 1·2단계 (정지 모기): 각각 10~20회 학습 반복 안에 통과
- 현재 병목: 3단계 (느리게 비행하는 모기)
  - 포획률 0.6대 도달, 승급 기준 0.8을 향해 보상 구조 수정 효과 검증 중
  - 잘 풀리는 에피소드는 보상이 양수 전환 — 시간 벌점을 상쇄할 만큼 빠른 포획 성공

## 6. 시사점

- **보상 설계가 알고리즘보다 지배적**
  - 학습 정체의 원인은 한 번도 알고리즘 버그가 아니었음
  - 보상의 귀속 시점, 시도의 한계비용 구조가 정책의 성격을 결정
  - 같은 목표라도 벌점으로 누르는 설계와 보너스로 당기는 설계는 전혀 다른 학습 동역학 생성
- **보상을 예측하는 데 필요한 정보는 관측에 있어야 함**
  - 혀 준비 상태, 무실수 여부, 최근 발사 횟수는 모두 보상 구조와 함께 추가된 관측
  - 가치 함수가 원리적으로 예측할 수 없는 보상은 학습에 잡음으로 작용함을 실험으로 확인
- **진단 지표가 시행착오 비용을 절감**
  - 발사 엔트로피 + 발사 시도율 두 지표로 "난사 대 발사 기피" 갈림길을 측정으로 확정
  - 지표가 없었다면 반대 방향 처방(벌점 강화)으로 문제를 악화시켰을 것
- **커리큘럼 승급 기준은 난이도 구조를 고려해야 함**
  - 전멸 여부 대신 포획률 채택 → 목표 마리 수 증가 시 요구 실력이 거듭제곱으로 커지는 함정 회피
- **남은 과제**
  - 단기: 3단계 돌파, 상위 단계(빠른 비행·여러 마리) 검증
  - 장기: 학습된 정책의 실물 소형 로봇 이식, 시뮬레이션과 현실의 간극 측정

> 🖼️ **PPT 이미지 제안** — 마무리 슬라이드: 시뮬레이션 스크린샷 → 실물 로봇 컨셉 일러스트로 이어지는 화살표 한 장 (sim-to-real 로드맵).

[curriculum] start stage: 3 저속비행
[   10] stage=3 steps= 102400 | ep_reward=1.55 | succ=0.76 | len=259 timeout=0.22 | policy=-0.0013 value=0.2922 ent_c=5.6598 ent_d=0.0112 fire=0.01 | kl=0.0050 clip=0.05 ev=0.51
[   20] stage=3 steps= 204800 | ep_reward=1.18 | succ=0.70 | len=270 timeout=0.22 | policy=-0.0019 value=0.2983 ent_c=5.6344 ent_d=0.0060 fire=0.01 | kl=0.0041 clip=0.04 ev=0.43
[curriculum] advance → 4 정상비행 (success_rate=0.82)
[   30] stage=4 steps= 307200 | ep_reward=0.47 | succ=0.78 | len=407 timeout=0.26 | policy=-0.0030 value=0.1568 ent_c=5.6281 ent_d=0.0037 fire=0.01 | kl=0.0062 clip=0.08 ev=0.46
[curriculum] advance → 5 3마리 (success_rate=0.88)
[   40] stage=5 steps= 409600 | ep_reward=-0.24 | succ=0.68 | len=705 timeout=0.42 | policy=-0.0031 value=0.1001 ent_c=5.6486 ent_d=0.0104 fire=0.02 | kl=0.0054 clip=0.06 ev=0.48
[   50] stage=5 steps= 512000 | ep_reward=-3.22 | succ=0.63 | len=906 timeout=0.80 | policy=-0.0025 value=0.0364 ent_c=5.6493 ent_d=0.0088 fire=0.01 | kl=0.0053 clip=0.06 ev=0.50
[   60] stage=5 steps= 614400 | ep_reward=-0.54 | succ=0.77 | len=687 timeout=0.54 | policy=-0.0010 value=0.0600 ent_c=5.6510 ent_d=0.0154 fire=0.01 | kl=0.0071 clip=0.09 ev=0.60
[   70] stage=5 steps= 716800 | ep_reward=-2.04 | succ=0.71 | len=758 timeout=0.67 | policy=-0.0030 value=0.0777 ent_c=5.6793 ent_d=0.0195 fire=0.01 | kl=0.0051 clip=0.06 ev=0.62
[   80] stage=5 steps= 819200 | ep_reward=-1.58 | succ=0.70 | len=739 timeout=0.78 | policy=-0.0031 value=0.0408 ent_c=5.6894 ent_d=0.0507 fire=0.03 | kl=0.0037 clip=0.04 ev=0.74
[   90] stage=5 steps= 921600 | ep_reward=0.96 | succ=0.72 | len=527 timeout=0.38 | policy=-0.0030 value=0.1184 ent_c=5.7010 ent_d=0.0184 fire=0.02 | kl=0.0047 clip=0.05 ev=0.64
[  100] stage=5 steps=1024000 | ep_reward=-0.04 | succ=0.73 | len=548 timeout=0.38 | policy=-0.0020 value=0.1284 ent_c=5.7211 ent_d=0.0636 fire=0.03 | kl=0.0054 clip=0.06 ev=0.55
  saved → results\run6\model_100.pt
[  110] stage=5 steps=1126400 | ep_reward=-1.57 | succ=0.67 | len=695 timeout=0.50 | policy=-0.0009 value=0.0743 ent_c=5.7336 ent_d=0.2353 fire=0.12 | kl=0.0042 clip=0.03 ev=0.68
[  120] stage=5 steps=1228800 | ep_reward=-0.66 | succ=0.66 | len=671 timeout=0.67 | policy=-0.0008 value=0.0789 ent_c=5.7527 ent_d=0.1834 fire=0.09 | kl=0.0055 clip=0.06 ev=0.75
[  130] stage=5 steps=1331200 | ep_reward=-2.71 | succ=0.73 | len=787 timeout=0.73 | policy=-0.0020 value=0.0471 ent_c=5.7686 ent_d=0.3436 fire=0.24 | kl=0.0063 clip=0.08 ev=0.83
[  140] stage=5 steps=1433600 | ep_reward=-1.21 | succ=0.69 | len=744 timeout=0.64 | policy=-0.0019 value=0.0701 ent_c=5.7721 ent_d=0.2028 fire=0.11 | kl=0.0058 clip=0.07 ev=0.75
[  150] stage=5 steps=1536000 | ep_reward=-2.30 | succ=0.67 | len=706 timeout=0.58 | policy=-0.0018 value=0.1058 ent_c=5.7745 ent_d=0.0956 fire=0.06 | kl=0.0044 clip=0.05 ev=0.66
[  160] stage=5 steps=1638400 | ep_reward=-1.28 | succ=0.67 | len=746 timeout=0.64 | policy=-0.0031 value=0.0642 ent_c=5.7675 ent_d=0.1766 fire=0.12 | kl=0.0067 clip=0.09 ev=0.80
[  170] stage=5 steps=1740800 | ep_reward=-2.02 | succ=0.68 | len=705 timeout=0.70 | policy=-0.0034 value=0.0618 ent_c=5.7569 ent_d=0.1720 fire=0.10 | kl=0.0101 clip=0.13 ev=0.81
[  180] stage=5 steps=1843200 | ep_reward=-2.54 | succ=0.65 | len=795 timeout=0.70 | policy=-0.0029 value=0.0915 ent_c=5.7530 ent_d=0.1271 fire=0.08 | kl=0.0058 clip=0.06 ev=0.61
[  190] stage=5 steps=1945600 | ep_reward=-1.42 | succ=0.68 | len=822 timeout=0.80 | policy=-0.0022 value=0.0460 ent_c=5.7602 ent_d=0.0058 fire=0.00 | kl=0.0040 clip=0.04 ev=0.66
[  200] stage=5 steps=2048000 | ep_reward=-2.06 | succ=0.65 | len=589 timeout=0.31 | policy=-0.0023 value=0.1663 ent_c=5.7485 ent_d=0.1767 fire=0.12 | kl=0.0055 clip=0.06 ev=0.47
  saved → results\run6\model_200.pt
[  210] stage=5 steps=2150400 | ep_reward=-2.37 | succ=0.71 | len=594 timeout=0.50 | policy=-0.0032 value=0.1010 ent_c=5.7354 ent_d=0.0959 fire=0.09 | kl=0.0070 clip=0.09 ev=0.64
[  220] stage=5 steps=2252800 | ep_reward=0.46 | succ=0.67 | len=572 timeout=0.54 | policy=-0.0027 value=0.1093 ent_c=5.7456 ent_d=0.0115 fire=0.01 | kl=0.0038 clip=0.04 ev=0.65
[  230] stage=5 steps=2355200 | ep_reward=0.91 | succ=0.75 | len=666 timeout=0.23 | policy=-0.0018 value=0.1445 ent_c=5.7552 ent_d=0.0148 fire=0.01 | kl=0.0045 clip=0.05 ev=0.60
[curriculum] advance → 6 3~10마리 (success_rate=0.81)
[  240] stage=6 steps=2457600 | ep_reward=1.22 | succ=0.71 | len=856 timeout=0.90 | policy=-0.0008 value=0.0888 ent_c=5.7376 ent_d=0.0143 fire=0.01 | kl=0.0058 clip=0.06 ev=0.86
[  250] stage=6 steps=2560000 | ep_reward=0.74 | succ=0.69 | len=740 timeout=0.60 | policy=-0.0024 value=0.1196 ent_c=5.7439 ent_d=0.0227 fire=0.02 | kl=0.0047 clip=0.05 ev=0.88
[  260] stage=6 steps=2662400 | ep_reward=-0.20 | succ=0.67 | len=843 timeout=0.60 | policy=-0.0012 value=0.0986 ent_c=5.7572 ent_d=0.0128 fire=0.01 | kl=0.0040 clip=0.03 ev=0.82
[  270] stage=6 steps=2764800 | ep_reward=-0.67 | succ=0.66 | len=913 timeout=0.80 | policy=-0.0023 value=0.0925 ent_c=5.7542 ent_d=0.0196 fire=0.02 | kl=0.0046 clip=0.05 ev=0.88
[  280] stage=6 steps=2867200 | ep_reward=-0.82 | succ=0.65 | len=880 timeout=0.78 | policy=-0.0035 value=0.0927 ent_c=5.7604 ent_d=0.0109 fire=0.01 | kl=0.0056 clip=0.07 ev=0.89
[  290] stage=6 steps=2969600 | ep_reward=0.28 | succ=0.68 | len=868 timeout=0.80 | policy=-0.0021 value=0.1004 ent_c=5.7588 ent_d=0.0119 fire=0.01 | kl=0.0048 clip=0.05 ev=0.84
[  300] stage=6 steps=3072000 | ep_reward=0.46 | succ=0.70 | len=643 timeout=0.69 | policy=-0.0030 value=0.1432 ent_c=5.7718 ent_d=0.0096 fire=0.01 | kl=0.0053 clip=0.06 ev=0.73
  saved → results\run6\model_300.pt
[  310] stage=6 steps=3174400 | ep_reward=0.18 | succ=0.70 | len=1014 timeout=0.88 | policy=-0.0035 value=0.0693 ent_c=5.7425 ent_d=0.0148 fire=0.01 | kl=0.0050 clip=0.05 ev=0.87
[  320] stage=6 steps=3276800 | ep_reward=-0.24 | succ=0.68 | len=673 timeout=0.80 | policy=-0.0032 value=0.1135 ent_c=5.7483 ent_d=0.0068 fire=0.01 | kl=0.0059 clip=0.06 ev=0.78
[  330] stage=6 steps=3379200 | ep_reward=0.31 | succ=0.73 | len=770 timeout=0.73 | policy=-0.0035 value=0.0680 ent_c=5.7404 ent_d=0.0101 fire=0.01 | kl=0.0043 clip=0.05 ev=0.85
[  340] stage=6 steps=3481600 | ep_reward=1.60 | succ=0.64 | len=766 timeout=0.73 | policy=-0.0017 value=0.1069 ent_c=5.7153 ent_d=0.0119 fire=0.01 | kl=0.0051 clip=0.05 ev=0.82
[  350] stage=6 steps=3584000 | ep_reward=-0.01 | succ=0.68 | len=738 timeout=0.67 | policy=-0.0026 value=0.1062 ent_c=5.7066 ent_d=0.0114 fire=0.02 | kl=0.0057 clip=0.06 ev=0.80
[  360] stage=6 steps=3686400 | ep_reward=-0.08 | succ=0.61 | len=809 timeout=0.89 | policy=-0.0033 value=0.0536 ent_c=5.7149 ent_d=0.0430 fire=0.02 | kl=0.0056 clip=0.07 ev=0.88
[  370] stage=6 steps=3788800 | ep_reward=0.10 | succ=0.70 | len=952 timeout=0.88 | policy=-0.0024 value=0.0531 ent_c=5.7173 ent_d=0.0098 fire=0.01 | kl=0.0056 clip=0.07 ev=0.93
[  380] stage=6 steps=3891200 | ep_reward=-1.26 | succ=0.64 | len=700 timeout=0.78 | policy=-0.0020 value=0.0878 ent_c=5.6847 ent_d=0.0209 fire=0.01 | kl=0.0061 clip=0.07 ev=0.82
[  390] stage=6 steps=3993600 | ep_reward=1.69 | succ=0.66 | len=920 timeout=0.90 | policy=-0.0011 value=0.0830 ent_c=5.6789 ent_d=0.0237 fire=0.02 | kl=0.0042 clip=0.04 ev=0.96
[  400] stage=6 steps=4096000 | ep_reward=-3.31 | succ=0.67 | len=1000 timeout=0.75 | policy=-0.0026 value=0.0603 ent_c=5.6450 ent_d=0.1255 fire=0.08 | kl=0.0077 clip=0.10 ev=0.91
  saved → results\run6\model_400.pt
[  410] stage=6 steps=4198400 | ep_reward=2.06 | succ=0.76 | len=752 timeout=0.40 | policy=-0.0015 value=0.1488 ent_c=5.6555 ent_d=0.0656 fire=0.04 | kl=0.0051 clip=0.06 ev=0.82
[  420] stage=6 steps=4300800 | ep_reward=-0.00 | succ=0.72 | len=765 timeout=0.70 | policy=-0.0018 value=0.1132 ent_c=5.6252 ent_d=0.0817 fire=0.05 | kl=0.0042 clip=0.04 ev=0.92
[  430] stage=6 steps=4403200 | ep_reward=-0.34 | succ=0.70 | len=720 timeout=0.60 | policy=-0.0022 value=0.1323 ent_c=5.6013 ent_d=0.0283 fire=0.02 | kl=0.0045 clip=0.04 ev=0.84
[  440] stage=6 steps=4505600 | ep_reward=1.14 | succ=0.69 | len=730 timeout=0.73 | policy=-0.0022 value=0.1124 ent_c=5.5952 ent_d=0.1151 fire=0.10 | kl=0.0061 clip=0.07 ev=0.85
[  450] stage=6 steps=4608000 | ep_reward=-1.07 | succ=0.75 | len=961 timeout=0.89 | policy=-0.0025 value=0.0794 ent_c=5.5837 ent_d=0.0143 fire=0.02 | kl=0.0052 clip=0.05 ev=0.87
[  460] stage=6 steps=4710400 | ep_reward=-0.69 | succ=0.73 | len=927 timeout=1.00 | policy=-0.0028 value=0.0479 ent_c=5.5850 ent_d=0.0659 fire=0.04 | kl=0.0052 clip=0.06 ev=0.91
[  470] stage=6 steps=4812800 | ep_reward=-0.71 | succ=0.73 | len=965 timeout=0.75 | policy=-0.0010 value=0.0686 ent_c=5.5671 ent_d=0.0098 fire=0.01 | kl=0.0037 clip=0.04 ev=0.90
[  480] stage=6 steps=4915200 | ep_reward=-1.79 | succ=0.67 | len=918 timeout=1.00 | policy=-0.0025 value=0.0502 ent_c=5.5769 ent_d=0.0402 fire=0.03 | kl=0.0055 clip=0.06 ev=0.94
[  490] stage=6 steps=5017600 | ep_reward=0.30 | succ=0.77 | len=757 timeout=0.50 | policy=-0.0040 value=0.1398 ent_c=5.5782 ent_d=0.0076 fire=0.01 | kl=0.0054 clip=0.05 ev=0.84
[  500] stage=6 steps=5120000 | ep_reward=0.29 | succ=0.73 | len=822 timeout=0.80 | policy=-0.0033 value=0.0836 ent_c=5.5608 ent_d=0.0102 fire=0.01 | kl=0.0055 clip=0.06 ev=0.90
  saved → results\run6\model_500.pt
[  510] stage=6 steps=5222400 | ep_reward=1.41 | succ=0.74 | len=792 timeout=0.89 | policy=-0.0001 value=0.0786 ent_c=5.5609 ent_d=0.0079 fire=0.01 | kl=0.0040 clip=0.04 ev=0.89
[  520] stage=6 steps=5324800 | ep_reward=-1.16 | succ=0.65 | len=965 timeout=0.89 | policy=-0.0035 value=0.0605 ent_c=5.5541 ent_d=0.0103 fire=0.02 | kl=0.0057 clip=0.07 ev=0.87
[  530] stage=6 steps=5427200 | ep_reward=0.24 | succ=0.72 | len=918 timeout=0.89 | policy=-0.0011 value=0.0696 ent_c=5.5559 ent_d=0.0081 fire=0.01 | kl=0.0061 clip=0.07 ev=0.90
[  540] stage=6 steps=5529600 | ep_reward=-2.15 | succ=0.74 | len=893 timeout=0.78 | policy=-0.0010 value=0.0572 ent_c=5.5413 ent_d=0.0096 fire=0.01 | kl=0.0058 clip=0.07 ev=0.89
[  550] stage=6 steps=5632000 | ep_reward=-1.28 | succ=0.67 | len=727 timeout=0.80 | policy=-0.0029 value=0.1422 ent_c=5.5436 ent_d=0.0070 fire=0.01 | kl=0.0063 clip=0.08 ev=0.82
[  560] stage=6 steps=5734400 | ep_reward=2.36 | succ=0.73 | len=796 timeout=0.70 | policy=-0.0027 value=0.0982 ent_c=5.5412 ent_d=0.0073 fire=0.01 | kl=0.0052 clip=0.06 ev=0.86
[  570] stage=6 steps=5836800 | ep_reward=0.93 | succ=0.74 | len=640 timeout=0.60 | policy=-0.0022 value=0.1173 ent_c=5.5024 ent_d=0.0229 fire=0.02 | kl=0.0056 clip=0.06 ev=0.85
[  580] stage=6 steps=5939200 | ep_reward=0.90 | succ=0.68 | len=727 timeout=0.58 | policy=-0.0026 value=0.1330 ent_c=5.4697 ent_d=0.0139 fire=0.01 | kl=0.0048 clip=0.05 ev=0.82
[  590] stage=6 steps=6041600 | ep_reward=2.54 | succ=0.77 | len=876 timeout=0.80 | policy=-0.0030 value=0.0807 ent_c=5.4658 ent_d=0.0124 fire=0.02 | kl=0.0056 clip=0.06 ev=0.93
[  600] stage=6 steps=6144000 | ep_reward=2.18 | succ=0.72 | len=749 timeout=0.75 | policy=-0.0014 value=0.1138 ent_c=5.4890 ent_d=0.0345 fire=0.02 | kl=0.0060 clip=0.06 ev=0.87
  saved → results\run6\model_600.pt
[  610] stage=6 steps=6246400 | ep_reward=-0.28 | succ=0.72 | len=772 timeout=0.89 | policy=-0.0026 value=0.0644 ent_c=5.4517 ent_d=0.0081 fire=0.01 | kl=0.0057 clip=0.06 ev=0.93
[  620] stage=6 steps=6348800 | ep_reward=-0.76 | succ=0.73 | len=889 timeout=1.00 | policy=-0.0019 value=0.0320 ent_c=5.4392 ent_d=0.0072 fire=0.01 | kl=0.0047 clip=0.05 ev=0.92
[  630] stage=6 steps=6451200 | ep_reward=0.42 | succ=0.71 | len=902 timeout=1.00 | policy=-0.0020 value=0.0466 ent_c=5.4157 ent_d=0.0060 fire=0.01 | kl=0.0057 clip=0.07 ev=0.96
[  640] stage=6 steps=6553600 | ep_reward=0.39 | succ=0.74 | len=790 timeout=0.82 | policy=-0.0026 value=0.0567 ent_c=5.3760 ent_d=0.0058 fire=0.01 | kl=0.0061 clip=0.07 ev=0.90
[  650] stage=6 steps=6656000 | ep_reward=0.30 | succ=0.68 | len=897 timeout=0.89 | policy=-0.0025 value=0.0917 ent_c=5.3831 ent_d=0.0107 fire=0.01 | kl=0.0056 clip=0.06 ev=0.87
[  660] stage=6 steps=6758400 | ep_reward=1.45 | succ=0.70 | len=753 timeout=0.78 | policy=-0.0018 value=0.0834 ent_c=5.3658 ent_d=0.0118 fire=0.01 | kl=0.0065 clip=0.08 ev=0.92
[  670] stage=6 steps=6860800 | ep_reward=1.77 | succ=0.72 | len=867 timeout=0.90 | policy=-0.0013 value=0.0645 ent_c=5.3407 ent_d=0.0076 fire=0.01 | kl=0.0084 clip=0.11 ev=0.91
[  680] stage=6 steps=6963200 | ep_reward=2.17 | succ=0.80 | len=747 timeout=0.70 | policy=-0.0009 value=0.0939 ent_c=5.3372 ent_d=0.0075 fire=0.01 | kl=0.0066 clip=0.08 ev=0.83
[  690] stage=6 steps=7065600 | ep_reward=2.68 | succ=0.76 | len=672 timeout=0.55 | policy=-0.0012 value=0.1182 ent_c=5.3081 ent_d=0.0078 fire=0.01 | kl=0.0054 clip=0.06 ev=0.67
[  700] stage=6 steps=7168000 | ep_reward=0.28 | succ=0.71 | len=897 timeout=0.80 | policy=-0.0017 value=0.0720 ent_c=5.3058 ent_d=0.0426 fire=0.03 | kl=0.0052 clip=0.05 ev=0.92
  saved → results\run6\model_700.pt
[  710] stage=6 steps=7270400 | ep_reward=-1.66 | succ=0.70 | len=807 timeout=0.78 | policy=-0.0006 value=0.0618 ent_c=5.2759 ent_d=0.0295 fire=0.02 | kl=0.0056 clip=0.06 ev=0.91
[  720] stage=6 steps=7372800 | ep_reward=0.38 | succ=0.72 | len=842 timeout=0.70 | policy=-0.0016 value=0.0846 ent_c=5.2692 ent_d=0.0552 fire=0.03 | kl=0.0059 clip=0.07 ev=0.92
[  730] stage=6 steps=7475200 | ep_reward=-1.02 | succ=0.71 | len=810 timeout=0.90 | policy=-0.0029 value=0.0641 ent_c=5.2496 ent_d=0.2061 fire=0.16 | kl=0.0064 clip=0.08 ev=0.87
[  740] stage=6 steps=7577600 | ep_reward=0.43 | succ=0.70 | len=754 timeout=0.73 | policy=-0.0022 value=0.1039 ent_c=5.2322 ent_d=0.0185 fire=0.01 | kl=0.0045 clip=0.05 ev=0.83
[  750] stage=6 steps=7680000 | ep_reward=2.71 | succ=0.74 | len=783 timeout=0.64 | policy=-0.0029 value=0.1073 ent_c=5.2102 ent_d=0.0148 fire=0.01 | kl=0.0052 clip=0.05 ev=0.86
[  760] stage=6 steps=7782400 | ep_reward=-0.53 | succ=0.67 | len=776 timeout=0.89 | policy=-0.0034 value=0.0835 ent_c=5.1787 ent_d=0.0071 fire=0.01 | kl=0.0059 clip=0.07 ev=0.89
[  770] stage=6 steps=7884800 | ep_reward=1.74 | succ=0.77 | len=878 timeout=0.67 | policy=-0.0015 value=0.0954 ent_c=5.1484 ent_d=0.0063 fire=0.01 | kl=0.0074 clip=0.10 ev=0.90
[  780] stage=6 steps=7987200 | ep_reward=2.26 | succ=0.71 | len=769 timeout=0.73 | policy=-0.0024 value=0.0909 ent_c=5.1234 ent_d=0.0181 fire=0.01 | kl=0.0065 clip=0.08 ev=0.91
[  790] stage=6 steps=8089600 | ep_reward=-0.27 | succ=0.70 | len=958 timeout=0.88 | policy=0.0004 value=0.0549 ent_c=5.1158 ent_d=0.0066 fire=0.01 | kl=0.0055 clip=0.06 ev=0.94
[  800] stage=6 steps=8192000 | ep_reward=2.17 | succ=0.71 | len=840 timeout=0.78 | policy=-0.0025 value=0.0854 ent_c=5.0933 ent_d=0.0070 fire=0.01 | kl=0.0050 clip=0.05 ev=0.87
  saved → results\run6\model_800.pt
[  810] stage=6 steps=8294400 | ep_reward=-0.08 | succ=0.68 | len=824 timeout=0.70 | policy=-0.0006 value=0.0884 ent_c=5.0846 ent_d=0.0760 fire=0.07 | kl=0.0066 clip=0.08 ev=0.88
[  820] stage=6 steps=8396800 | ep_reward=0.82 | succ=0.74 | len=875 timeout=0.78 | policy=-0.0043 value=0.0689 ent_c=5.0487 ent_d=0.0055 fire=0.01 | kl=0.0075 clip=0.09 ev=0.91
[  830] stage=6 steps=8499200 | ep_reward=0.53 | succ=0.78 | len=911 timeout=0.89 | policy=-0.0012 value=0.0690 ent_c=5.0452 ent_d=0.0513 fire=0.08 | kl=0.0080 clip=0.10 ev=0.93
[  840] stage=6 steps=8601600 | ep_reward=0.14 | succ=0.74 | len=847 timeout=1.00 | policy=-0.0019 value=0.0517 ent_c=5.0476 ent_d=0.0780 fire=0.07 | kl=0.0077 clip=0.09 ev=0.93
[  850] stage=6 steps=8704000 | ep_reward=1.04 | succ=0.71 | len=670 timeout=0.78 | policy=-0.0023 value=0.1263 ent_c=5.0354 ent_d=0.0105 fire=0.01 | kl=0.0070 clip=0.08 ev=0.77
[  860] stage=6 steps=8806400 | ep_reward=0.92 | succ=0.67 | len=794 timeout=0.73 | policy=-0.0022 value=0.0947 ent_c=5.0314 ent_d=0.0066 fire=0.01 | kl=0.0049 clip=0.05 ev=0.86
[  870] stage=6 steps=8908800 | ep_reward=-1.42 | succ=0.72 | len=830 timeout=1.00 | policy=-0.0010 value=0.0364 ent_c=5.0473 ent_d=0.0064 fire=0.01 | kl=0.0073 clip=0.09 ev=0.92
[  880] stage=6 steps=9011200 | ep_reward=-0.10 | succ=0.75 | len=890 timeout=0.78 | policy=-0.0010 value=0.1123 ent_c=5.0589 ent_d=0.0052 fire=0.00 | kl=0.0068 clip=0.08 ev=0.83
[  890] stage=6 steps=9113600 | ep_reward=0.38 | succ=0.71 | len=749 timeout=0.70 | policy=-0.0022 value=0.0953 ent_c=5.0455 ent_d=0.0099 fire=0.02 | kl=0.0087 clip=0.11 ev=0.89
[  900] stage=6 steps=9216000 | ep_reward=-0.83 | succ=0.68 | len=887 timeout=0.89 | policy=-0.0011 value=0.0713 ent_c=5.0193 ent_d=0.0452 fire=0.04 | kl=0.0060 clip=0.07 ev=0.89
  saved → results\run6\model_900.pt
[  910] stage=6 steps=9318400 | ep_reward=1.82 | succ=0.71 | len=693 timeout=0.55 | policy=-0.0021 value=0.1778 ent_c=4.9920 ent_d=0.0095 fire=0.01 | kl=0.0064 clip=0.07 ev=0.77
[  920] stage=6 steps=9420800 | ep_reward=-0.03 | succ=0.70 | len=764 timeout=0.89 | policy=-0.0023 value=0.0474 ent_c=4.9970 ent_d=0.0178 fire=0.01 | kl=0.0066 clip=0.08 ev=0.91
[  930] stage=6 steps=9523200 | ep_reward=1.87 | succ=0.69 | len=709 timeout=0.67 | policy=-0.0017 value=0.1628 ent_c=4.9802 ent_d=0.0101 fire=0.01 | kl=0.0058 clip=0.06 ev=0.86