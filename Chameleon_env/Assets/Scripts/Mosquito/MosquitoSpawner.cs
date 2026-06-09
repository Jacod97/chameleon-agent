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

            int n = Random.Range(cMin, cMax + 1);
            for (int i = 0; i < n; i++)
            {
                Vector3 pos = new Vector3(
                    Random.Range(lo.x, hi.x),
                    Random.Range(lo.y, hi.y),
                    Random.Range(lo.z, hi.z)
                );
                var m = Instantiate(mosquitoPrefab, pos, Quaternion.identity, transform);
                _alive.Add(m);
            }
        }

        private void Update()
        {
            // TongueController 가 Destroy 한 모기를 캐시에서 제거
            for (int i = _alive.Count - 1; i >= 0; i--)
            {
                if (_alive[i] == null) _alive.RemoveAt(i);
            }
        }
    }
}
