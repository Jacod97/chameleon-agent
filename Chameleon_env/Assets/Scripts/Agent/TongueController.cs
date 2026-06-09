using UnityEngine;

namespace ChameleonRL
{
    /// <summary>
    /// 혀 발사·복귀·충돌·흡착·끌어당김 제어.
    /// 상태 머신: Idle → Extending → Retracting → Idle.
    /// 사이클 중 추가 발사 요청은 무시 (= 자연 쿨다운).
    /// </summary>
    public class TongueController : MonoBehaviour
    {
        public enum TongueState { Idle, Extending, Retracting }

        [Header("씬 참조")]
        public Transform muzzle;
        public Transform tongueTip;
        public LineRenderer lineRenderer;

        [Header("혀 파라미터 (현실 반영)")]
        public float maxRange = 2.5f;
        public float cycleSeconds = 0.3f;
        [Tooltip("흡착 시 가구를 카멜레온 쪽으로 끌어당기는 impulse")]
        public float adhesionImpulse = 4f;

        [Header("히트 판정")]
        [Tooltip("Mosquito + Furniture + Room 레이어")]
        public LayerMask hitMask;

        [Tooltip("포획 허용 반경 — 혀 끝 흡착 면적. 0이면 가는 선(raycast)처럼 동작. " +
                 "작은 모기를 대략 조준만 해도 잡히게 하는 값")]
        public float catchRadius = 0.15f;

        public TongueState State { get; private set; } = TongueState.Idle;

        private ChameleonAgent _agent;
        private float _cycleTime;
        private GameObject _attachedObject;
        private bool _caughtMosquito;
        private Vector3 _hitPointLocal;
        private int _mosquitoLayer = -1;
        private int _furnitureLayer = -1;

        private void Awake()
        {
            _agent = GetComponentInParent<ChameleonAgent>();
            // fail-fast: 보상 전달 대상이 없으면 포획/미스 보상이 조용히 사라짐
            if (_agent == null) throw new System.InvalidOperationException("[TongueController] 부모에 ChameleonAgent 없음");

            if (lineRenderer != null)
            {
                lineRenderer.positionCount = 2;  // 시각화 라인 두 끝점 (optional)
                lineRenderer.enabled = false;
            }
            if (tongueTip != null) tongueTip.gameObject.SetActive(false);

            // Layer 캐싱. 미등록이면 포획/끌림 판정이 조용히 영영 안 되므로 즉시 중단
            _mosquitoLayer = LayerMask.NameToLayer("Mosquito");
            _furnitureLayer = LayerMask.NameToLayer("Furniture");
            if (_mosquitoLayer < 0) throw new System.InvalidOperationException("[TongueController] 'Mosquito' Layer 미등록 — Project Settings > Tags and Layers 에 추가 필요");
            if (_furnitureLayer < 0) throw new System.InvalidOperationException("[TongueController] 'Furniture' Layer 미등록");
        }

        /// <summary>
        /// ChameleonAgent 가 호출. Idle 상태일 때만 발사.
        /// </summary>
        public bool TryFire()
        {
            if (State != TongueState.Idle) return false;

            State = TongueState.Extending;
            _cycleTime = 0f;
            _attachedObject = null;
            _caughtMosquito = false;
            _hitPointLocal = Vector3.zero;

            if (lineRenderer != null) lineRenderer.enabled = true;
            if (tongueTip != null) tongueTip.gameObject.SetActive(true);

            // 발사 순간 spherecast 로 첫 충돌 지점 확정 (catchRadius 만큼 허용 반경)
            if (Physics.SphereCast(muzzle.position, catchRadius, muzzle.forward, out RaycastHit hit,
                maxRange, hitMask, QueryTriggerInteraction.Collide))
            {
                _hitPointLocal = muzzle.InverseTransformPoint(hit.point);

                int hitLayer = hit.collider.gameObject.layer;
                if (hitLayer == _mosquitoLayer)
                {
                    _caughtMosquito = true;
                    _attachedObject = hit.collider.gameObject;
                }
                else if (hitLayer == _furnitureLayer)
                {
                    _attachedObject = hit.collider.attachedRigidbody != null
                        ? hit.collider.attachedRigidbody.gameObject
                        : hit.collider.gameObject;
                    TryPullFurniture(_attachedObject);
                }
                else
                {
                    _attachedObject = hit.collider.gameObject;
                }
            }
            else
            {
                _hitPointLocal = new Vector3(0f, 0f, maxRange);
            }

            return true;
        }

        private void Update()
        {
            if (State == TongueState.Idle) return;

            _cycleTime += Time.deltaTime;
            float halfCycle = cycleSeconds * 0.5f;

            float t;
            if (_cycleTime < halfCycle)
            {
                State = TongueState.Extending;
                t = _cycleTime / halfCycle;
            }
            else if (_cycleTime < cycleSeconds)
            {
                State = TongueState.Retracting;
                t = 1f - (_cycleTime - halfCycle) / halfCycle;
            }
            else
            {
                FinishCycle();
                return;
            }

            // 시각화 — muzzle 부터 hitPoint 까지 t 만큼
            Vector3 startWorld = muzzle.position;
            Vector3 hitWorld = muzzle.TransformPoint(_hitPointLocal);
            Vector3 currentTipWorld = Vector3.Lerp(startWorld, hitWorld, t);

            lineRenderer.SetPosition(0, startWorld);
            lineRenderer.SetPosition(1, currentTipWorld);
            tongueTip.position = currentTipWorld;

            // 모기 캐치 시 끝에 붙여 가져옴
            if (_caughtMosquito && _attachedObject != null && State == TongueState.Retracting)
            {
                _attachedObject.transform.position = currentTipWorld;
            }
        }

        private void FinishCycle()
        {
            if (_caughtMosquito && _attachedObject != null)
            {
                _agent.OnMosquitoCaught();
                Destroy(_attachedObject);
            }
            else
            {
                _agent.OnAttackMissed();
            }

            State = TongueState.Idle;
            _attachedObject = null;
            _caughtMosquito = false;
            _cycleTime = 0f;

            if (lineRenderer != null) lineRenderer.enabled = false;
            if (tongueTip != null) tongueTip.gameObject.SetActive(false);
        }

        /// <summary>
        /// 흡착된 가구에 카멜레온 쪽으로 향하는 impulse 부여.
        /// 가벼우면 빨려오고, 무거우면 거의 안 움직임.
        /// </summary>
        private void TryPullFurniture(GameObject furniture)
        {
            var rb = furniture.GetComponent<Rigidbody>();
            if (rb == null) return;
            Vector3 toMuzzle = (muzzle.position - rb.worldCenterOfMass).normalized;
            rb.AddForce(toMuzzle * adhesionImpulse, ForceMode.Impulse);
        }

        /// <summary>
        /// ChameleonAgent.OnEpisodeBegin 에서 호출.
        /// </summary>
        public void ResetState()
        {
            State = TongueState.Idle;
            _cycleTime = 0f;
            _attachedObject = null;
            _caughtMosquito = false;
            if (lineRenderer != null) lineRenderer.enabled = false;
            if (tongueTip != null) tongueTip.gameObject.SetActive(false);
        }
    }
}
