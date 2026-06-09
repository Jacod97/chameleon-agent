using Unity.MLAgents;
using Unity.MLAgents.Actuators;
using Unity.MLAgents.Sensors;
using UnityEngine;
using UnityEngine.InputSystem;

namespace ChameleonRL
{
    /// <summary>
    /// 카멜레온 에이전트. Unity ML-Agents Agent 를 상속.
    /// 관측 7-dim 벡터 + PointNet BufferSensor (모기 집합).
    /// 행동 연속 4 + 이산 2 (대기/혀발사).
    /// 보상: r_catch + r_miss + r_time + r_approach + r_break + r_success.
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

        private Vector3 _initialPosition;
        private Quaternion _initialRotation;
        private Rigidbody _rb;
        private int _catches;
        private int _misses;

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
        }

        [Header("관측 정규화")]
        [Tooltip("위치 정규화 기준 (방 반치수 = 3.5m)")]
        public float positionNormScale = 3.5f;

        [Tooltip("속도 정규화 기준 (max 이동 속도 ~0.5)")]
        public float velocityNormScale = 1.0f;

        [Tooltip("머리 pitch 정규화 기준 (clamp 절댓값 max ~60도)")]
        public float pitchNormScale = 60f;

        public override void CollectObservations(VectorSensor sensor)
        {
            // 벡터 관측 7-dim (docs/RL_Design.md §3.1)
            // 위치 (방 원점 기준 절대), 방 반치수로 정규화 [-1, 1]
            sensor.AddObservation(transform.position.x / positionNormScale);
            sensor.AddObservation(transform.position.z / positionNormScale);
            // 속도 [-1, 1] 근사
            sensor.AddObservation(_rb.linearVelocity.x / velocityNormScale);
            sensor.AddObservation(_rb.linearVelocity.z / velocityNormScale);

            // 머리 각도 정규화
            float headPitch = NormalizeAngle(headPitchPivot.localEulerAngles.x);
            float headYaw = NormalizeAngle(headPivot.localEulerAngles.y);
            sensor.AddObservation(headPitch / pitchNormScale);  // [-60/60, 45/60] ≈ [-1, 0.75]
            sensor.AddObservation(headYaw / 180f);              // [-1, 1]

            // 남은 모기 수 (max 10 기준)
            int remainingMosquitoes = GetRemainingMosquitoCount();
            sensor.AddObservation(remainingMosquitoes / 10f);

            // PointNet (BufferSensorComponent) 입력 채우기
            mosquitoSensor.Tick();
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

            // 머리 yaw
            float headYawDelta = yawHeadCmd * maxYawRateHead * dt;
            headPivot.Rotate(Vector3.up, headYawDelta, Space.Self);

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

            // 성공 종료: 모든 모기 잡음
            if (mosquitoSpawner.AliveCount == 0)
            {
                AddReward(+rewardConfig.successBonus);
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
        }

        public void OnAttackMissed()
        {
            AddReward(-rewardConfig.missPenalty);
            _misses++;
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
