using Unity.MLAgents;
using UnityEngine;

namespace ChameleonRL
{
    /// <summary>
    /// 모기 한 마리의 행동 — 비행 ↔ 착지 반복.
    /// 카멜레온 존재 인식 X. 회피 행동 없음.
    /// </summary>
    public class Mosquito : MonoBehaviour
    {
        public enum MosquitoState { Flying, Landed }

        [Header("비행 파라미터 (현실 반영)")]
        public float flyingSpeed = 1.0f;
        public float minFlightSeconds = 1.0f;
        public float maxFlightSeconds = 4.0f;
        public float minLandedSeconds = 0.5f;
        public float maxLandedSeconds = 3.0f;

        [Header("진행 방향 변화")]
        public float directionChangeRate = 1.5f;

        [Header("착지 판정")]
        [Tooltip("Room + Furniture 레이어")]
        public LayerMask landingMask;

        [Tooltip("착지할 표면을 탐색하는 최대 거리")]
        public float landingSearchRange = 5f;

        [Tooltip("표면에 이 거리 이내로 접근하면 착지 확정")]
        public float landSnapDistance = 0.15f;

        [Header("방 내부 경계 (안 넘어가도록)")]
        public Vector3 roomMin = new Vector3(-3.4f, 0.05f, -3.4f);
        public Vector3 roomMax = new Vector3(3.4f, 2.95f, 3.4f);

        public MosquitoState State { get; private set; } = MosquitoState.Flying;
        public Vector3 Velocity { get; private set; }

        private Vector3 _direction;
        private float _stateTimer;
        private float _stateDuration;
        private float _directionTimer;
        private bool _seekingLanding;
        private Vector3 _landTargetPoint;
        private Vector3 _landNormal;
        private bool _stationary;     // 커리큘럼: true면 스폰 자리에 완전 정지
        private Vector3 _areaOrigin;  // 병렬 영역 중심(부모=스포너 위치) — x,z 경계 기준

        private void Start()
        {
            // 병렬 영역 지원: 부모(스포너) 위치를 이 모기가 속한 영역 중심으로 사용
            _areaOrigin = transform.parent != null ? transform.parent.position : Vector3.zero;
            // 커리큘럼 난이도 파라미터 (Python EnvironmentParametersChannel 에서 주입)
            var ep = Academy.Instance.EnvironmentParameters;
            _stationary = ep.GetWithDefault("mosquito_stationary", 0f) > 0.5f;
            flyingSpeed *= ep.GetWithDefault("mosquito_speed_scale", 1f);  // 비행 속도 배율
            PickNewDirection();
            EnterFlying();
        }

        private void Update()
        {
            if (_stationary) { Velocity = Vector3.zero; return; }  // 정지 단계: 안 움직임
            _stateTimer += Time.deltaTime;
            if (State == MosquitoState.Flying) TickFlying();
            else TickLanded();
        }

        private void TickFlying()
        {
            // 착지 표면을 찾은 상태면 그 표면을 향해 직진 → 도착 시 착지
            if (_seekingLanding)
            {
                Vector3 toTarget = _landTargetPoint - transform.position;
                float remaining = toTarget.magnitude;
                if (remaining > 1e-4f) _direction = toTarget / remaining;
                transform.position += _direction * flyingSpeed * Time.deltaTime;
                Velocity = _direction * flyingSpeed;

                if (remaining <= landSnapDistance)
                {
                    transform.position = _landTargetPoint + _landNormal * 0.005f;
                    EnterLanded();
                }
                return;
            }

            _directionTimer += Time.deltaTime;
            if (_directionTimer >= 1f / Mathf.Max(0.01f, directionChangeRate))
            {
                _directionTimer = 0f;
                PickNewDirection();
            }

            Vector3 step = _direction * flyingSpeed * Time.deltaTime;
            Vector3 next = transform.position + step;

            // 방 경계 안에서 튕기기 (x,z 는 영역 중심 기준 상대, y 높이는 절대)
            if (next.x < _areaOrigin.x + roomMin.x || next.x > _areaOrigin.x + roomMax.x) _direction.x = -_direction.x;
            if (next.y < roomMin.y || next.y > roomMax.y) _direction.y = -_direction.y;
            if (next.z < _areaOrigin.z + roomMin.z || next.z > _areaOrigin.z + roomMax.z) _direction.z = -_direction.z;

            step = _direction * flyingSpeed * Time.deltaTime;
            transform.position += step;
            Velocity = _direction * flyingSpeed;

            // 비행 시간이 끝나면 가까운 표면을 찾아 착지하러 간다
            if (_stateTimer >= _stateDuration)
            {
                if (FindLandingSurface()) _seekingLanding = true;
                else EnterFlying();   // 표면 못 찾으면 비행 연장
            }
        }

        private void TickLanded()
        {
            Velocity = Vector3.zero;
            if (_stateTimer >= _stateDuration)
            {
                EnterFlying();
                PickNewDirection();
            }
        }

        // 여러 방향으로 탐색해 가장 가까운 표면(벽·천장·가구)을 착지 목표로 선택
        private bool FindLandingSurface()
        {
            Vector3[] dirs =
            {
                _direction,
                Vector3.down, Vector3.up,
                Vector3.left, Vector3.right,
                Vector3.forward, Vector3.back,
            };

            float best = float.MaxValue;
            bool found = false;
            foreach (var dir in dirs)
            {
                if (Physics.Raycast(transform.position, dir.normalized, out RaycastHit hit,
                    landingSearchRange, landingMask))
                {
                    if (hit.distance < best)
                    {
                        best = hit.distance;
                        _landTargetPoint = hit.point;
                        _landNormal = hit.normal;
                        found = true;
                    }
                }
            }
            return found;
        }

        private void EnterFlying()
        {
            State = MosquitoState.Flying;
            _seekingLanding = false;
            _stateTimer = 0f;
            _stateDuration = Random.Range(minFlightSeconds, maxFlightSeconds);
        }

        private void EnterLanded()
        {
            State = MosquitoState.Landed;
            _seekingLanding = false;
            _stateTimer = 0f;
            _stateDuration = Random.Range(minLandedSeconds, maxLandedSeconds);
        }

        private void PickNewDirection()
        {
            _direction = Random.onUnitSphere;
            _direction.y *= 0.5f;  // 천장으로만 직진 방지
            _direction.Normalize();
        }
    }
}
