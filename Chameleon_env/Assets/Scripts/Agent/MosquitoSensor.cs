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

        [Header("Occlusion 차단 레이어 (Room + Furniture)")]
        public LayerMask occlusionMask;

        private BufferSensorComponent _buffer;
        private float _prevNearestDist = float.MaxValue;

        private void Awake()
        {
            _buffer = GetComponent<BufferSensorComponent>();
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
            if (spawner == null || headCamera == null) return;

            float halfFovCos = Mathf.Cos(fovDegrees * 0.5f * Mathf.Deg2Rad);
            float nearest = float.MaxValue;

            foreach (var m in spawner.Alive)
            {
                if (m == null) continue;

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
                    relVel.x,
                    relVel.y,
                    relVel.z,
                };
                _buffer.AppendObservation(obs);

                if (dist < nearest) nearest = dist;
            }

            // r_approach: 시야 안 최근접 거리 감소 시 +
            if (nearest < float.MaxValue && _prevNearestDist < float.MaxValue)
            {
                float reduction = _prevNearestDist - nearest;
                if (reduction > 0f && agent != null) agent.OnApproach(reduction);
            }
            _prevNearestDist = nearest;
        }
    }
}
