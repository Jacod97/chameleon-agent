using Unity.MLAgents;
using Unity.MLAgents.Actuators;
using Unity.MLAgents.Sensors;
using UnityEngine;
using UnityEngine.InputSystem;

namespace ChameleonRL
{
    /// <summary>
    /// 카멜레온 에이전트. Unity ML-Agents Agent 를 상속.
    /// 관측 11-dim 벡터 + PointNet BufferSensor (모기 집합).
    /// 행동 연속 4 + 이산 2 (대기/혀발사).
    /// 보상: r_catch + r_miss + r_time + r_approach + r_break + r_success + r_precision + r_efficiency + r_missed.
    /// 종료: 전지적 전멸 판정 대신 "일정 시간 무감지 → 임무 완료 선언" (현실 반영 — 로봇은 잔여 수를 모름).
    /// </summary>
    [RequireComponent(typeof(Rigidbody))]
    public class ChameleonAgent : Agent
    {
        [Header("이동 파라미터")]
        public float maxForwardSpeed = 0.5f;
        public float maxBackwardSpeed = 0.3f;
        public float maxYawRateBody = 120f;

        [Header("머리 회전 파라미터")]
        public float maxYawRateHead = 180f;
        public float maxPitchRateHead = 120f;
        public Vector2 pitchClamp = new Vector2(-60f, 45f);
        [Tooltip("머리 yaw 제한. 무제한 회전 시 ±180° 관측 불연속이 생겨 가치 학습을 방해")]
        public Vector2 yawClamp = new Vector2(-90f, 90f);

        [Header("씬 참조")]
        public Transform headPivot;
        public Transform headPitchPivot;
        public Transform tongueMuzzle;
        public FurnitureRegistry furnitureRegistry;
        public TongueController tongueController;
        public MosquitoSpawner mosquitoSpawner;
        public MosquitoSensor mosquitoSensor;

        [Header("보상")]
        public RewardConfig rewardConfig;

        [Header("탐지 기반 성공 판정")]
        [Tooltip("이 시간(초) 동안 모기가 한 마리도 감지되지 않으면 임무 완료로 선언하고 에피소드 종료. " +
                 "실제로 전멸이면 성공 보상, 남아 있으면 마리당 missedMosquitoPenalty 벌점. " +
                 "15s 는 정상 비행(1m/s) 표적 재획득에 부족 — run7 4단계 0.51 횡보로 확인, 25s 로 완화")]
        public float noDetectionSuccessSeconds = 25f;

        private Vector3 _initialPosition;
        private Quaternion _initialRotation;
        private Rigidbody _rb;
        private int _catches;
        private int _misses;
        private int _shotsSinceLastCatch;
        private int _decisionsSinceDetection;
        private int _noDetectionThresholdDecisions;

        public override void Initialize()
        {
            _rb = GetComponent<Rigidbody>();
            _initialPosition = transform.position;
            _initialRotation = transform.rotation;

            // fail-fast: 필수 참조 누락은 절대 정상이 아니므로 즉시 중단 (조용히 진행 금지)
            if (headPivot == null) throw new System.InvalidOperationException("[ChameleonAgent] headPivot 미설정 — Inspector 배선 필요");
            if (headPitchPivot == null) throw new System.InvalidOperationException("[ChameleonAgent] headPitchPivot 미설정");
            if (tongueMuzzle == null) throw new System.InvalidOperationException("[ChameleonAgent] tongueMuzzle 미설정");
            if (furnitureRegistry == null) throw new System.InvalidOperationException("[ChameleonAgent] furnitureRegistry 미설정");
            if (tongueController == null) throw new System.InvalidOperationException("[ChameleonAgent] tongueController 미설정");
            if (mosquitoSpawner == null) throw new System.InvalidOperationException("[ChameleonAgent] mosquitoSpawner 미설정");
            if (mosquitoSensor == null) throw new System.InvalidOperationException("[ChameleonAgent] mosquitoSensor 미설정");
            if (rewardConfig == null) throw new System.InvalidOperationException("[ChameleonAgent] rewardConfig 미설정");
            if (mosquitoSpawner.mosquitoPrefab == null) throw new System.InvalidOperationException("[ChameleonAgent] mosquitoSpawner.mosquitoPrefab 미설정");

            var decisionRequester = GetComponent<DecisionRequester>();
            if (decisionRequester == null) throw new System.InvalidOperationException("[ChameleonAgent] DecisionRequester 미부착");
            float decisionIntervalSeconds = Time.fixedDeltaTime * decisionRequester.DecisionPeriod;
            _noDetectionThresholdDecisions = Mathf.CeilToInt(noDetectionSuccessSeconds / decisionIntervalSeconds);
        }

        public override void OnEpisodeBegin()
        {
            // ① 카멜레온 위치·회전·속도 리셋
            transform.position = _initialPosition;
            transform.rotation = _initialRotation;
            _rb.linearVelocity = Vector3.zero;
            _rb.angularVelocity = Vector3.zero;

            // ② 머리 회전 초기화
            headPivot.localEulerAngles = Vector3.zero;
            headPitchPivot.localEulerAngles = Vector3.zero;

            // ③ 가구 리셋 (먼저 — 모기가 가구 위에 착지할 수 있으므로)
            furnitureRegistry.ResetAll();

            // ④ 모기 재스폰
            mosquitoSpawner.RespawnAll();

            // ⑤ 혀 리셋
            tongueController.ResetState();

            // ⑥ 센서 내부 캐시 리셋
            mosquitoSensor.ResetState();

            // ⑦ 카운터 리셋
            _catches = 0;
            _misses = 0;
            _shotsSinceLastCatch = 0;
            _decisionsSinceDetection = 0;
        }

        [Header("관측 정규화")]
        [Tooltip("위치 정규화 기준 (방 반치수 = 3.5m)")]
        public float positionNormScale = 3.5f;

        [Tooltip("속도 정규화 기준 (max 이동 속도 = maxForwardSpeed 값과 맞출 것)")]
        public float velocityNormScale = 0.5f;

        [Tooltip("머리 pitch 정규화 기준 (clamp 절댓값 max ~60도)")]
        public float pitchNormScale = 60f;

        public override void CollectObservations(VectorSensor sensor)
        {
            // 벡터 관측 10-dim (docs/RL_Design.md §3.1)
            // 위치 = 자기 영역(방 중앙=초기 위치) 기준 상대좌표. 병렬 복제 시 영역 오프셋과 무관하게 [-1,1] 유지
            Vector3 relativePosition = transform.position - _initialPosition;
            sensor.AddObservation(relativePosition.x / positionNormScale);
            sensor.AddObservation(relativePosition.z / positionNormScale);
            // 속도: 로컬 좌표계 (몸체 방향 기준). 월드 좌표 쓰면 회전 각도에 따라 같은 행동이 다른 관측 생성.
            Vector3 localVelocity = transform.InverseTransformDirection(_rb.linearVelocity);
            sensor.AddObservation(localVelocity.x / velocityNormScale);
            sensor.AddObservation(localVelocity.z / velocityNormScale);

            // 머리 각도 정규화 (yaw 는 clamp 범위 기준 — 불연속 없음)
            float headPitch = NormalizeAngle(headPitchPivot.localEulerAngles.x);
            float headYaw = NormalizeAngle(headPivot.localEulerAngles.y);
            sensor.AddObservation(headPitch / pitchNormScale);  // [-60/60, 45/60] ≈ [-1, 0.75]
            sensor.AddObservation(headYaw / yawClamp.y);        // [-1, 1]

            // 남은 모기 수 (max 10 기준)
            int remainingMosquitoes = GetRemainingMosquitoCount();
            sensor.AddObservation(remainingMosquitoes / 10f);

            // 혀 준비 상태 — 쿨다운(사이클) 중 발사 무효를 에이전트가 알 수 있게 (POMDP 해소)
            sensor.AddObservation(tongueController.State == TongueController.TongueState.Idle ? 1f : 0f);

            // 무실수 플래그 — precision bonus(+2) 수령 가능 여부. 없으면 가치함수가 원리적으로 예측 불가
            sensor.AddObservation(_misses == 0 ? 1f : 0f);

            // 직전 포획 이후 발사 수 — efficiency bonus 수령 가능 여부 (window 에서 포화, 1.0 = 보너스 소멸)
            sensor.AddObservation(Mathf.Min(_shotsSinceLastCatch, rewardConfig.efficiencyShotWindow)
                                  / (float)rewardConfig.efficiencyShotWindow);

            // PointNet (BufferSensorComponent) 입력 채우기
            mosquitoSensor.Tick();

            // 무감지 경과 비율 — 1.0 도달 시 임무 완료 선언으로 종료. 없으면 종료·벌점이 가치함수에 예측 불가
            if (mosquitoSensor.DetectedCount > 0) _decisionsSinceDetection = 0;
            else _decisionsSinceDetection++;
            sensor.AddObservation(Mathf.Min(1f, _decisionsSinceDetection / (float)_noDetectionThresholdDecisions));
        }

        public override void OnActionReceived(ActionBuffers actions)
        {
            float moveCmd = Mathf.Clamp(actions.ContinuousActions[0], -1f, 1f);
            float yawBodyCmd = Mathf.Clamp(actions.ContinuousActions[1], -1f, 1f);
            float yawHeadCmd = Mathf.Clamp(actions.ContinuousActions[2], -1f, 1f);
            float pitchHeadCmd = Mathf.Clamp(actions.ContinuousActions[3], -1f, 1f);

            float dt = Time.fixedDeltaTime;

            // 차체 이동
            float speed = moveCmd >= 0f
                ? moveCmd * maxForwardSpeed
                : moveCmd * maxBackwardSpeed;
            Vector3 forward = transform.forward;
            Vector3 horizontalVelocity = forward * speed;
            _rb.linearVelocity = new Vector3(horizontalVelocity.x, _rb.linearVelocity.y, horizontalVelocity.z);

            // 차체 yaw 회전 (탱크형 제자리 가능)
            float bodyYawDelta = yawBodyCmd * maxYawRateBody * dt;
            transform.Rotate(Vector3.up, bodyYawDelta, Space.World);

            // 머리 yaw (clamp — 무제한 회전 방지)
            float headYawDelta = yawHeadCmd * maxYawRateHead * dt;
            float currentYaw = NormalizeAngle(headPivot.localEulerAngles.y);
            float newYaw = Mathf.Clamp(currentYaw + headYawDelta, yawClamp.x, yawClamp.y);
            headPivot.localEulerAngles = new Vector3(0f, newYaw, 0f);

            // 머리 pitch (clamp)
            float headPitchDelta = pitchHeadCmd * maxPitchRateHead * dt;
            Vector3 pitchEuler = headPitchPivot.localEulerAngles;
            float currentPitch = NormalizeAngle(pitchEuler.x);
            float newPitch = Mathf.Clamp(currentPitch + headPitchDelta, pitchClamp.x, pitchClamp.y);
            headPitchPivot.localEulerAngles = new Vector3(newPitch, 0f, 0f);

            // 이산 액션: 혀 발사
            int attackCmd = actions.DiscreteActions[0];
            if (attackCmd == 1)
            {
                tongueController.TryFire();
            }

            // 시간 패널티
            AddReward(-rewardConfig.timePenaltyPerStep);

            // 가구 파손 → 실패 종료
            if (furnitureRegistry.AnyBroken())
            {
                AddReward(-rewardConfig.breakPenalty);
                EndEpisode();
                return;
            }

            // 임무 완료 선언: 일정 시간 무감지 = 성공 (실사용 요구는 "주변에 모기가 없을 것" — 숨어서
            // 한 번도 안 보인 모기까지 책임지지 않음). 정밀 보상은 실제 전멸 + 무실수일 때만.
            // 잔존 벌점은 외면 보상 해킹이 관측되면 재활성용으로 유지 (현재 asset 값 0)
            if (_decisionsSinceDetection >= _noDetectionThresholdDecisions)
            {
                AddReward(+rewardConfig.successBonus);
                if (mosquitoSpawner.AliveCount == 0)
                {
                    if (_misses == 0 && rewardConfig.precisionBonus > 0f)
                        AddReward(+rewardConfig.precisionBonus);
                }
                else
                {
                    AddReward(-rewardConfig.missedMosquitoPenalty * mosquitoSpawner.AliveCount);
                }
                EndEpisode();
            }
        }

        public override void Heuristic(in ActionBuffers actionsOut)
        {
            var c = actionsOut.ContinuousActions;
            var d = actionsOut.DiscreteActions;

            var kb = Keyboard.current;
            if (kb == null)
            {
                c[0] = 0f; c[1] = 0f; c[2] = 0f; c[3] = 0f;
                d[0] = 0;
                return;
            }

            // 전/후진: W/S 또는 위/아래 화살표 — 단 위/아래 화살표는 머리 pitch 도 겸하므로 W/S 우선
            c[0] = (kb.wKey.isPressed ? 1f : 0f) - (kb.sKey.isPressed ? 1f : 0f);
            // 차체 yaw: A/D
            c[1] = (kb.dKey.isPressed ? 1f : 0f) - (kb.aKey.isPressed ? 1f : 0f);
            // 머리 yaw: ← / →
            c[2] = (kb.rightArrowKey.isPressed ? 1f : 0f) - (kb.leftArrowKey.isPressed ? 1f : 0f);
            // 머리 pitch: ↑ / ↓ (↑ = 위로 = -pitch, ↓ = 아래로 = +pitch)
            c[3] = (kb.upArrowKey.isPressed ? -1f : 0f) + (kb.downArrowKey.isPressed ? 1f : 0f);
            // 혀 발사: Space
            d[0] = kb.spaceKey.isPressed ? 1 : 0;
        }

        // ---------- 외부 hook ----------

        public void OnMosquitoCaught()
        {
            AddReward(+rewardConfig.catchReward);
            _catches++;
            _shotsSinceLastCatch++;
            if (rewardConfig.efficiencyBonus > 0f
                && _shotsSinceLastCatch <= rewardConfig.efficiencyShotWindow)
            {
                AddReward(+rewardConfig.efficiencyBonus);
            }
            _shotsSinceLastCatch = 0;
        }

        public void OnAttackMissed()
        {
            AddReward(-rewardConfig.missPenalty);
            _misses++;
            _shotsSinceLastCatch++;
        }

        public void OnApproach(float distanceReduction)
        {
            AddReward(rewardConfig.approachCoeff * distanceReduction);
        }

        private int GetRemainingMosquitoCount()
        {
            return mosquitoSpawner.AliveCount;
        }

        private static float NormalizeAngle(float deg)
        {
            deg = deg % 360f;
            if (deg > 180f) deg -= 360f;
            if (deg < -180f) deg += 360f;
            return deg;
        }
    }
}
