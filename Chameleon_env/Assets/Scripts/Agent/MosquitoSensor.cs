using Unity.MLAgents.Sensors;
using UnityEngine;

namespace ChameleonRL
{
    /// <summary>
    /// 매 결정 스텝마다 BufferSensorComponent 에 모기 관측을 Append.
    /// 머리 기준 상대 좌표, 시야 + occlusion 통과한 모기만.
    /// docs/RL_Design.md §3.1 ②.
    /// </summary>
    [RequireComponent(typeof(BufferSensorComponent))]
    public class MosquitoSensor : MonoBehaviour
    {
        [Header("씬 참조")]
        public Transform headCamera;
        public MosquitoSpawner spawner;
        public ChameleonAgent agent;

        [Header("시야 파라미터 (docs/RL_Design.md §2.2)")]
        public float fovDegrees = 90f;
        public float maxDetectRange = 3f;

        [Tooltip("속도 정규화 기준. Mosquito.flyingSpeed 기본값(1.0)과 맞출 것. " +
                 "커리큘럼 mosquito_speed_scale 최대치에 맞게 조정 필요.")]
        public float maxMosquitoSpeed = 1.0f;

        [Header("Occlusion 차단 레이어 (Room + Furniture)")]
        public LayerMask occlusionMask;

        /// <summary>직전 Tick 에서 시야·차폐 판정을 통과한 모기 수</summary>
        public int DetectedCount { get; private set; }

        private BufferSensorComponent _buffer;
        private float _prevNearestDist = float.MaxValue;

        private void Awake()
        {
            _buffer = GetComponent<BufferSensorComponent>();
            // fail-fast: 누락 시 관측·접근보상이 조용히 사라져 에이전트가 장님이 됨
            if (spawner == null) throw new System.InvalidOperationException("[MosquitoSensor] spawner 미설정");
            if (headCamera == null) throw new System.InvalidOperationException("[MosquitoSensor] headCamera 미설정");
            if (agent == null) throw new System.InvalidOperationException("[MosquitoSensor] agent 미설정");
        }

        public void ResetState()
        {
            _prevNearestDist = float.MaxValue;
        }

        /// <summary>
        /// ChameleonAgent.CollectObservations 안에서 호출.
        /// </summary>
        public void Tick()
        {
            // 참조는 Awake 에서 검증됨 (null 이면 거기서 이미 중단)

            float halfFovCos = Mathf.Cos(fovDegrees * 0.5f * Mathf.Deg2Rad);
            float nearest = float.MaxValue;
            DetectedCount = 0;

            // Alive 는 포획 즉시 동기 제거되므로 null/파괴 객체가 섞일 수 없음 (섞이면 그게 버그)
            foreach (var m in spawner.Alive)
            {
                Vector3 toMosquito = m.transform.position - headCamera.position;
                float dist = toMosquito.magnitude;
                if (dist > maxDetectRange) continue;

                // FOV 체크
                float cosAngle = Vector3.Dot(headCamera.forward, toMosquito.normalized);
                if (cosAngle < halfFovCos) continue;

                // Occlusion 체크 (가구·벽 뒤 모기는 안 보임)
                if (Physics.Raycast(headCamera.position, toMosquito.normalized,
                    out RaycastHit hit, dist, occlusionMask, QueryTriggerInteraction.Ignore))
                {
                    if (hit.collider.gameObject != m.gameObject) continue;
                }

                // BufferSensor 에 6-dim 관측 추가 (머리 기준 상대)
                Vector3 relPos = headCamera.InverseTransformPoint(m.transform.position);
                Vector3 relVel = headCamera.InverseTransformDirection(m.Velocity);

                float[] obs = new float[6]
                {
                    relPos.x / maxDetectRange,
                    relPos.y / maxDetectRange,
                    relPos.z / maxDetectRange,
                    relVel.x / maxMosquitoSpeed,
                    relVel.y / maxMosquitoSpeed,
                    relVel.z / maxMosquitoSpeed,
                };
                _buffer.AppendObservation(obs);
                DetectedCount++;

                if (dist < nearest) nearest = dist;
            }

            // r_approach: 시야 안 최근접 거리 감소 시 +
            if (nearest < float.MaxValue && _prevNearestDist < float.MaxValue)
            {
                float reduction = _prevNearestDist - nearest;
                if (reduction > 0f) agent.OnApproach(reduction);
            }
            _prevNearestDist = nearest;
        }
    }
}
