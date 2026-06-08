using System.Collections.Generic;
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

            // prefab 미설정 시 스폰 스킵 (사용자가 모기 에셋 받기 전 학습 동작 검증용)
            if (mosquitoPrefab == null)
            {
                Debug.LogWarning("[MosquitoSpawner] mosquitoPrefab 미설정 — 스폰 건너뜀");
                return;
            }

            int n = Random.Range(minCount, maxCount + 1);
            for (int i = 0; i < n; i++)
            {
                Vector3 pos = new Vector3(
                    Random.Range(spawnMin.x, spawnMax.x),
                    Random.Range(spawnMin.y, spawnMax.y),
                    Random.Range(spawnMin.z, spawnMax.z)
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
