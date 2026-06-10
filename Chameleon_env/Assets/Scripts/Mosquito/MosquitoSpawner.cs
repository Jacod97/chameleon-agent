using System.Collections.Generic;
using Unity.MLAgents;
using UnityEngine;

namespace ChameleonRL
{
    /// <summary>
    /// 매 에피소드 시작 시 모기 3~10마리를 방 안 임의 공중 위치에 스폰.
    /// ChameleonAgent 가 AliveCount 를 조회.
    /// </summary>
    public class MosquitoSpawner : MonoBehaviour
    {
        [Header("Prefab")]
        public Mosquito mosquitoPrefab;

        [Header("스폰 파라미터")]
        public int minCount = 3;
        public int maxCount = 10;

        [Header("방 안 스폰 영역")]
        public Vector3 spawnMin = new Vector3(-3.0f, 0.5f, -3.0f);
        public Vector3 spawnMax = new Vector3(3.0f, 2.5f, 3.0f);

        [Tooltip("정지(stationary) 커리큘럼 단계의 스폰 높이 상한. " +
                 "혀 최대 도달 높이(muzzle + 2.5×sin60° ≈ 2.2m)를 넘는 위치에 정지 모기가 스폰되면 " +
                 "영원히 잡을 수 없는 에피소드가 되어 커리큘럼이 영구 정체됨")]
        public float stationaryMaxSpawnY = 1.8f;

        public int AliveCount => _alive.Count;
        public IReadOnlyList<Mosquito> Alive => _alive;

        private readonly List<Mosquito> _alive = new();

        public void RespawnAll()
        {
            foreach (var m in _alive)
            {
                if (m != null) Destroy(m.gameObject);
            }
            _alive.Clear();

            // fail-fast: prefab 없으면 모기 0마리로 조용히 학습 진행(타겟 없음) → 즉시 중단
            if (mosquitoPrefab == null)
                throw new System.InvalidOperationException("[MosquitoSpawner] mosquitoPrefab 미설정 — 스폰 불가");

            // 커리큘럼 난이도 파라미터 (Python EnvironmentParametersChannel 에서 주입)
            var ep = Academy.Instance.EnvironmentParameters;
            int cMin = Mathf.RoundToInt(ep.GetWithDefault("mosquito_count_min", minCount));
            int cMax = Mathf.RoundToInt(ep.GetWithDefault("mosquito_count_max", maxCount));
            // spawn_scale 0→근접·저공, 1→방 전체. 단계적으로 탐색 난이도 조절
            float spawnScale = Mathf.Clamp01(ep.GetWithDefault("spawn_scale", 1f));
            Vector3 nearMin = new Vector3(-1.2f, 0.3f, -1.2f);
            Vector3 nearMax = new Vector3( 1.2f, 1.2f,  1.2f);
            Vector3 lo = Vector3.Lerp(nearMin, spawnMin, spawnScale);
            Vector3 hi = Vector3.Lerp(nearMax, spawnMax, spawnScale);

            // 정지 단계: 도달 불가능한 높이 스폰 차단 (도달 불가 에피소드 = 커리큘럼 정체)
            bool stationary = ep.GetWithDefault("mosquito_stationary", 0f) > 0.5f;
            if (stationary) hi.y = Mathf.Min(hi.y, stationaryMaxSpawnY);

            // 병렬 영역 지원: x,z 는 이 스포너(=영역) 위치 기준 상대, y(높이)는 절대(모든 영역 바닥 y=0)
            Vector3 areaOrigin = transform.position;
            int n = Random.Range(cMin, cMax + 1);
            for (int i = 0; i < n; i++)
            {
                Vector3 pos = new Vector3(
                    areaOrigin.x + Random.Range(lo.x, hi.x),
                    Random.Range(lo.y, hi.y),
                    areaOrigin.z + Random.Range(lo.z, hi.z)
                );
                var m = Instantiate(mosquitoPrefab, pos, Quaternion.identity, transform);
                _alive.Add(m);
            }
        }

        /// <summary>
        /// TongueController 가 포획 확정 순간 호출. 동기적으로 제거되어
        /// AliveCount·관측·전멸 판정이 같은 FixedUpdate 안에서 일관됨.
        /// (기존 렌더 프레임 Update 정리 방식은 time_scale 20 에서 수 decision 지연)
        /// </summary>
        public void Remove(Mosquito m)
        {
            if (!_alive.Remove(m))
                throw new System.InvalidOperationException(
                    $"[MosquitoSpawner] Alive 목록에 없는 모기 제거 시도: {m.name}");
        }
    }
}
