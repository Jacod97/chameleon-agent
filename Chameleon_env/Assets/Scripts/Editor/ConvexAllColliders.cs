using UnityEditor;
using UnityEngine;

namespace ChameleonRL.EditorTools
{
    /// <summary>
    /// 씬의 모든 MeshCollider 를 Convex 로 일괄 변경.
    /// 메뉴: Tools > ChameleonRL > Make All MeshColliders Convex
    /// </summary>
    public static class ConvexAllColliders
    {
        [MenuItem("Tools/ChameleonRL/Make All MeshColliders Convex")]
        public static void MakeAllConvex()
        {
            var colliders = Object.FindObjectsByType<MeshCollider>(FindObjectsSortMode.None);
            int changed = 0;
            int alreadyOk = 0;
            foreach (var c in colliders)
            {
                if (!c.convex)
                {
                    Undo.RecordObject(c, "Make MeshCollider Convex");
                    c.convex = true;
                    changed++;
                }
                else
                {
                    alreadyOk++;
                }
            }
            Debug.Log($"[ConvexAllColliders] {changed} 개 변경 / {alreadyOk} 개 이미 Convex / 총 {colliders.Length} 개 MeshCollider");
        }
    }
}
