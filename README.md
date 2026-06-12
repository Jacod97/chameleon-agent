# Chameleon Agent

> Unity 물리 가상환경에서 **모기를 자율 포획하는 소형 홈 로봇**을 강화학습으로 훈련하는 프로젝트.
> 표준 `mlagents-learn` 을 쓰지 않고 **PyTorch 로 PPO 학습 루프를 직접 구현**했다.

![Unity](https://img.shields.io/badge/Unity-6000.x-000000?logo=unity&logoColor=white)
![ML-Agents](https://img.shields.io/badge/ML--Agents-4.0.3-2196F3)
![Python](https://img.shields.io/badge/Python-3.10-3776AB?logo=python&logoColor=white)
![PyTorch](https://img.shields.io/badge/PyTorch-2.0%2B-EE4C2C?logo=pytorch&logoColor=white)
![Custom PPO](https://img.shields.io/badge/RL-Custom%20PPO-4CAF50)
![PointNet](https://img.shields.io/badge/Encoder-PointNet-9C27B0)
![Hybrid Action](https://img.shields.io/badge/Action-Hybrid%204C%2B1D-FF9800)
![MLflow](https://img.shields.io/badge/Tracking-MLflow-0194E2?logo=mlflow&logoColor=white)
![Hydra](https://img.shields.io/badge/Config-Hydra-89B8CD)

---

## 데모

<!-- TODO: 학습 장면 GIF / 환경 스크린샷 추가 예정 -->
> _데모 영상 / 스크린샷 추가 예정._

---

## 목차

- [무엇을 하는 프로젝트인가](#무엇을-하는-프로젝트인가)
  - [핵심 특징](#핵심-특징)
- [시작하기](#시작하기)
  - [요구 사항](#1-요구-사항)
  - [설치](#2-설치)
  - [Unity 환경 빌드](#3-unity-환경-빌드)
  - [학습 실행](#4-학습-실행)
  - [체크포인트에서 재개](#5-체크포인트에서-재개)
  - [학습 모니터링](#6-학습-모니터링)
  - [주요 설정](#주요-설정-configdefaultyaml)
- [시스템 구조](#시스템-구조)
  - [프로젝트 구조](#프로젝트-구조)
- [문서](#문서)
- [현재 상태](#현재-상태)
- [Summary](#summary)

---

## 무엇을 하는 프로젝트인가

7m×7m 원룸에 모기 3~10마리가 날아다닌다. 약 30cm 크기의 카멜레온 로봇이 돌아다니며 머리를 돌려 모기를 찾고, 사거리 2.5m의 혀를 발사해 잡는다. 제약은 둘:

1. 방 안 **모든 모기 포획**
2. 그 과정에서 **가구를 파손하지 않을 것** — 파손 시 즉시 실패 종료

가상에서 검증된 정책을 추후 실물 로봇으로 이식하는 것이 최종 목표라서, 게임적 단순화 없이 **현실 물리(중력·충돌·무게)** 를 그대로 반영한다.

### 핵심 특징

- **커스텀 PPO 직접 구현** — `mlagents-envs` + PyTorch 로 rollout 수집 · GAE · clipped update · 체크포인트까지 학습 루프 전체를 직접 작성 (`src/`)
- **Hybrid Action Space** — 연속 4(전후진·차체 yaw·머리 yaw·머리 pitch) + 이산 1(대기/혀 발사)을 한 정책에서 동시 출력 (Gaussian + Categorical)
- **PointNet 기반 가변 관측** — 시야에 들어온 모기 수가 매 스텝 달라지는 문제를, 모기 집합을 PointNet(포인트별 공유 MLP → max pooling)으로 인코딩해 고정 크기 특징으로 변환
- **부분 관측(POMDP)** — 머리 카메라 FOV 90° + occlusion(가구·벽 뒤 모기 안 보임) → 에이전트가 둘러보는 행동을 학습해야 함
- **포획률 기반 6단계 커리큘럼** — 정지 모기부터 3~10마리 비행까지, 최근 50 에피소드 평균 포획률 ≥ 0.8 달성 시 자동 승급

---

## 시작하기

### 1. 요구 사항

- **Python 3.10.x** — `mlagents-envs 1.1.0` 이 3.11+ 를 지원하지 않음
- **Unity 6 (6000.x)** + ML-Agents 4.0.3 패키지 — 빌드를 새로 만들 때만 필요
- GPU 선택 사항 (CUDA 가능 시 자동 사용)

### 2. 설치

```powershell
conda create -n unity_rl_310 python=3.10 -y
conda activate unity_rl_310
pip install -r requirements.txt
```

### 3. Unity 환경 빌드

`Chameleon_env/` 를 Unity 6 으로 열고 `MainEnv` 씬을 Windows Standalone 으로 빌드한다.
출력 경로는 설정 기본값에 맞춰 `Builds/MainEnv/Chameleon_env.exe` 권장 (다른 경로면 실행 시 `env_path=` 로 지정).

### 4. 학습 실행

```powershell
# 기본 실행 — config/default.yaml 의 설정 사용 (헤드리스 + 20배속)
python scripts/train.py

# 설정 오버라이드 (Hydra) — 예: 화면 보면서 10배속
python scripts/train.py no_graphics=false time_scale=10

# 빌드 대신 Unity 에디터에 연결 — 실행 후 에디터에서 Play 누르면 접속됨
python scripts/train.py env_path=null
```

### 5. 체크포인트에서 재개

```powershell
# 저장된 모델과 도달했던 커리큘럼 단계를 지정
python scripts/resume_train.py resume_path=results/run_01/model_400.pt start_stage=3
```

### 6. 학습 모니터링

```powershell
mlflow ui    # → http://localhost:5000 , experiment: chameleon-rl
```

- 추적 지표: 에피소드 보상 · 포획률(커리큘럼 승급 기준) · 손실 · **발사 엔트로피 / 발사 시도율** (발사 정책 이상 조기 경보)
- 모델 체크포인트는 `results/run_01/` 에 주기 저장 (`save_interval` 설정)

### 주요 설정 (`config/default.yaml`)

| 키 | 기본값 | 의미 |
|---|---|---|
| `env_path` | `Builds/MainEnv/Chameleon_env.exe` | 빌드 경로. `null` 이면 에디터 연결 |
| `time_scale` | 20 | 시뮬레이션 배속 |
| `no_graphics` | true | 헤드리스 실행 |
| `max_iterations` | 5000 | 학습 반복 횟수 |
| `resume_path` / `start_stage` | null / 1 | 재개용 체크포인트와 커리큘럼 단계 |
| `gamma` / `lam` / `clip_eps` | 0.995 / 0.95 / 0.2 | PPO 핵심 하이퍼파라미터 |

---

## 시스템 구조

```mermaid
flowchart LR
    ENV["Unity 환경<br/>원룸 7×7×3m · 가구 · 모기 3~10"]
    OENC["Observation Encoder<br/>(자기 상태 10D, MLP)"]
    PNET["PointNet<br/>(시야 안 모기 집합, 가변)"]
    FUSE["Fusion Encoder"]
    ACT["Actor<br/>Gaussian 4 + Categorical 1"]
    CRI["Critic<br/>V(s)"]
    BUF["RolloutBuffer<br/>(GAE)"]

    ENV --> OENC --> FUSE
    ENV --> PNET --> FUSE
    FUSE --> ACT
    FUSE --> CRI
    ACT -->|"행동"| ENV
    ENV -->|"보상"| BUF
    BUF -.->|"PPO 업데이트"| ACT
    BUF -.->|"PPO 업데이트"| CRI
```

학습은 **PPO**(Clipped Surrogate + GAE). On-policy 의 보수적 업데이트가 "가구 파손 회피" 제약에 유리하다.

### 프로젝트 구조

```
chameleon-agent/
├─ Chameleon_env/          # Unity 프로젝트 (씬 · 에이전트 · 모기 · 가구 스크립트)
├─ config/default.yaml     # 실행 · 하이퍼파라미터 설정 (Hydra)
├─ scripts/
│   ├─ train.py            # 학습 진입점
│   └─ resume_train.py     # 체크포인트 재개
├─ src/
│   ├─ network.py          # ActorCritic (MLP + PointNet)
│   ├─ ppo.py              # clipped update · 분리 엔트로피
│   ├─ buffer.py           # RolloutBuffer + GAE
│   ├─ communicator.py     # Unity ↔ Python 데이터 교환
│   ├─ curriculum.py       # 포획률 기반 6단계 커리큘럼
│   ├─ trainer.py          # 수집 → 갱신 루프
│   └─ logger.py           # MLflow 기록
├─ docs/objective_f.md     # 목적함수 · 학습 사이클 심층 분석
└─ report.md               # 프로젝트 보고서 (배경 · 설계 · 실험)
```

---

## 문서

| 문서 | 내용 |
|---|---|
| [`report.md`](report.md) | 프로젝트 보고서 — 배경 · 환경 · MDP · 학습 방법 · 실험 |
| [`docs/objective_f.md`](docs/objective_f.md) | 목적함수와 학습 사이클 분석 — GAE · 손실 · 수렴 과정 |

---

## 현재 상태

- [완료] 커스텀 PPO 트레이너 + Unity 연동, 헤드리스 배속 학습 파이프라인 가동
- [완료] 커리큘럼 1·2단계 (정지 모기) 통과
- [진행 중] 3단계 (저속 비행 모기) — 보상 구조 수정 효과 검증 중
- [예정] 상위 단계 학습 · 결과/데모 수집 · 실물 로봇 이식 검토

---

## Summary

| 항목 | 내용 |
|---|---|
| 목표 | 가구 파손 없이 방 안 모든 모기를 포획하는 자율 로봇 정책 학습 |
| 환경 | Unity 6 · 7×7×3m 원룸 · 현실 물리(중력·충돌·무게) · 부분 관측(FOV 90°, occlusion) |
| 관측 | 자기 상태 벡터 10D + PointNet 으로 인코딩한 가변 모기 집합 |
| 행동 | Hybrid — 연속 4 (이동·차체 회전·머리 yaw/pitch) + 이산 1 (혀 발사) |
| 알고리즘 | PyTorch 직접 구현 PPO — GAE · 연속/이산 분리 엔트로피 · 포획률 기반 6단계 커리큘럼 |
| 실험 추적 | MLflow — 보상 · 포획률 · 발사 엔트로피 · 발사 시도율 |
| 현재 | 커리큘럼 1·2단계 통과, 3단계(비행 모기) 검증 중 |

시뮬레이션에서 검증된 정책을 실물 소형 로봇으로 이식하는 것이 이 프로젝트의 최종 지향점이다.
설계·실험의 상세한 서사는 [`report.md`](report.md), 목적함수의 수학적 분석은 [`docs/objective_f.md`](docs/objective_f.md) 에 있다.
