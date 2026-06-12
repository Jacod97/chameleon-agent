using UnityEngine;

namespace ChameleonRL
{
    /// <summary>
    /// 보상 계수 일괄 관리. ScriptableObject 로 만들어 여러 환경에서 공유.
    /// docs/RL_Design.md §3.3 의 r_catch / r_miss / r_time / r_approach / r_break / r_success.
    /// </summary>
    [CreateAssetMenu(fileName = "RewardConfig", menuName = "ChameleonRL/Reward Config")]
    public class RewardConfig : ScriptableObject
    {
        [Header("모기 포획")]
        public float catchReward = 1.0f;

        [Header("허공 공격")]
        [Tooltip("부호는 코드에서 - 적용")]
        public float missPenalty = 0.05f;

        [Header("시간")]
        public float timePenaltyPerStep = 0.001f;

        [Header("접근 (Reward Shaping)")]
        [Tooltip("시야 안 최근접 모기 거리 감소량 × 이 계수. " +
                 "0.01 은 decision당 시간 패널티(0.005)의 30%에 불과해 shaping이 사실상 무효였음. " +
                 "3m 전진 시 누적 +0.15 — catch(1.0)보다 충분히 작아 보상 해킹 위험 없음")]
        public float approachCoeff = 0.05f;

        [Header("가구 파손")]
        [Tooltip("부호는 코드에서 - 적용. §3.3 '큰 음수' — catch(1.0)보다 충분히 크게. 실험으로 조정")]
        public float breakPenalty = 5.0f;

        [Header("완전 포획 보너스")]
        public float successBonus = 1.0f;

        [Header("정밀 사격 보너스 (희소 보상)")]
        [Tooltip("에피소드 내 헛스윙·가구 파손 없이 전멸 달성 시 추가 보상. 0이면 비활성.")]
        public float precisionBonus = 2.0f;

        [Header("효율 사격 보너스")]
        [Tooltip("직전 포획 이후 efficiencyShotWindow 발 이내에 포획 성공 시 추가 보상. " +
                 "헛발사 한계비용(0.05)이 catch(1.0) 대비 작아 난사가 기대값상 이득인 구조를 " +
                 "양수 보상으로 교정 — 패널티 강화와 달리 발사 탐색 붕괴 위험 없음. 0이면 비활성.")]
        public float efficiencyBonus = 0.5f;

        [Tooltip("효율 보너스 인정 발사 횟수 (포획한 그 발 포함)")]
        public int efficiencyShotWindow = 3;
    }
}
