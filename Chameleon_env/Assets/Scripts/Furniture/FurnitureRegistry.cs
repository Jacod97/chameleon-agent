using System.Collections.Generic;
using UnityEngine;

namespace ChameleonRL
{
    /// <summary>
    /// 씬의 모든 Furniture 일괄 관리. 에피소드 리셋·파손 여부 조회.
    /// 빈 GameObject 'Furniture' 에 부착.
    /// </summary>
    public class FurnitureRegistry : MonoBehaviour
    {
        public List<Furniture> All { get; private set; } = new();

        private void Awake()
        {
            All.AddRange(GetComponentsInChildren<Furniture>());
        }

        public bool AnyBroken()
        {
            foreach (var f in All)
            {
                if (f.IsBroken) return true;
            }
            return false;
        }

        public void ResetAll()
        {
            foreach (var f in All) f.ResetState();
        }
    }
}
