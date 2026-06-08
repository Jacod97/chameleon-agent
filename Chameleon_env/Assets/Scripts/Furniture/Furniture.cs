using UnityEngine;

namespace ChameleonRL
{
    /// <summary>
    /// 가구 하나의 상태. 충돌 충격이 임계를 넘으면 깨졌다고 표시.
    /// ChameleonAgent 가 매 스텝 IsBroken 을 확인하고 보상/종료 처리.
    /// </summary>
    [RequireComponent(typeof(Rigidbody))]
    public class Furniture : MonoBehaviour
    {
        [Header("파손")]
        [Tooltip("충돌 시 impulse 가 이 값 이상이면 파손. 무게는 Rigidbody.Mass 에서 직접 읽음")]
        public float breakImpulseThreshold = 5f;

        [Tooltip("파손 시 빨간 tint (디버그용)")]
        public bool tintWhenBroken = true;

        [Header("정착(Settling)")]
        [Tooltip("리셋 직후 이 시간 동안은 파손 판정 안 함 (가구가 자기 위치에 정착할 시간)")]
        public float settleDuration = 0.5f;

        public bool IsBroken { get; private set; }

        private Vector3 _initialPosition;
        private Quaternion _initialRotation;
        private Rigidbody _rb;
        private Renderer[] _renderers;
        private Color[] _originalColors;
        private float _settleStartTime;

        private void Awake()
        {
            _rb = GetComponent<Rigidbody>();
            _initialPosition = transform.position;
            _initialRotation = transform.rotation;
            _settleStartTime = Time.time;

            _renderers = GetComponentsInChildren<Renderer>();
            _originalColors = new Color[_renderers.Length];
            for (int i = 0; i < _renderers.Length; i++)
            {
                var m = _renderers[i].material;
                _originalColors[i] = m.HasProperty("_BaseColor")
                    ? m.GetColor("_BaseColor")
                    : m.color;
            }
        }

        [Header("디버그")]
        [Tooltip("켜면 OnCollisionEnter 의 impulse 값을 Console 에 출력")]
        public bool logImpulse = false;

        private void OnCollisionEnter(Collision collision)
        {
            if (IsBroken) return;
            // 정착 시간 동안은 자기 무게로 인한 충돌·진동을 파손으로 오판하지 않음
            if (Time.time - _settleStartTime < settleDuration) return;

            float impulse = collision.impulse.magnitude;
            if (logImpulse)
            {
                Debug.Log($"[Furniture:{gameObject.name}] impulse={impulse:F3} threshold={breakImpulseThreshold:F2} hit={collision.gameObject.name}");
            }
            if (impulse >= breakImpulseThreshold) MarkBroken();
        }

        private void MarkBroken()
        {
            IsBroken = true;
            if (tintWhenBroken)
            {
                foreach (var r in _renderers)
                {
                    if (r.material.HasProperty("_BaseColor"))
                        r.material.SetColor("_BaseColor", Color.red);
                    else
                        r.material.color = Color.red;
                }
            }
        }

        /// <summary>
        /// 에피소드 시작 시 ChameleonAgent 가 호출. 가구를 초기 상태로 복원.
        /// </summary>
        public void ResetState()
        {
            IsBroken = false;
            transform.position = _initialPosition;
            transform.rotation = _initialRotation;

            // Kinematic Rigidbody 는 velocity 설정 불가 (예: 벽걸이 가구)
            if (!_rb.isKinematic)
            {
                _rb.linearVelocity = Vector3.zero;
                _rb.angularVelocity = Vector3.zero;
            }

            // 리셋 후 정착 시간 다시 시작 — 자기 충돌로 파손 판정 방지
            _settleStartTime = Time.time;

            for (int i = 0; i < _renderers.Length; i++)
            {
                if (_renderers[i].material.HasProperty("_BaseColor"))
                    _renderers[i].material.SetColor("_BaseColor", _originalColors[i]);
                else
                    _renderers[i].material.color = _originalColors[i];
            }
        }
    }
}
