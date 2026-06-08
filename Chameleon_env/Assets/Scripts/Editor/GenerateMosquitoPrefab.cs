using UnityEditor;
using UnityEngine;

namespace ChameleonRL.EditorTools
{
    /// <summary>
    /// Mosquito placeholder prefab 자동 생성.
    /// Sphere visual + SphereCollider(Trigger) + Kinematic Rigidbody + Mosquito 스크립트.
    /// 메뉴: Tools > ChameleonRL > Generate Mosquito Placeholder Prefab
    /// </summary>
    public static class GenerateMosquitoPrefab
    {
        private const string PrefabPath = "Assets/Prefabs/Mosquito.prefab";

        [MenuItem("Tools/ChameleonRL/Generate Mosquito Placeholder Prefab")]
        public static void Generate()
        {
            int mosquitoLayer = LayerMask.NameToLayer("Mosquito");
            int roomLayer = LayerMask.NameToLayer("Room");
            int furnitureLayer = LayerMask.NameToLayer("Furniture");

            if (mosquitoLayer < 0 || roomLayer < 0 || furnitureLayer < 0)
            {
                Debug.LogError("[GenerateMosquito] Layer Mosquito/Room/Furniture 중 하나가 미등록. " +
                    "Edit > Project Settings > Tags and Layers 에서 User Layer 6~9 등록 후 다시 실행.");
                return;
            }

            // 부모 GameObject
            var mosquito = new GameObject("Mosquito");
            mosquito.layer = mosquitoLayer;

            // SphereCollider (Trigger, 0.5cm 반지름 = TongueController raycast 가 잡을 수 있음)
            var sc = mosquito.AddComponent<SphereCollider>();
            sc.isTrigger = true;
            sc.radius = 0.005f;

            // Rigidbody (Kinematic — 모기는 transform 으로 움직임. 가구·벽에 물리 충돌 안 줌)
            var rb = mosquito.AddComponent<Rigidbody>();
            rb.isKinematic = true;
            rb.useGravity = false;

            // Mosquito 스크립트
            var mscript = mosquito.AddComponent<ChameleonRL.Mosquito>();
            mscript.flyingSpeed = 1.0f;
            mscript.minFlightSeconds = 1.0f;
            mscript.maxFlightSeconds = 4.0f;
            mscript.minLandedSeconds = 0.5f;
            mscript.maxLandedSeconds = 3.0f;
            mscript.directionChangeRate = 1.0f;
            mscript.landingMask = (1 << roomLayer) | (1 << furnitureLayer);
            mscript.roomMin = new Vector3(-3.4f, 0.05f, -3.4f);
            mscript.roomMax = new Vector3(3.4f, 2.95f, 3.4f);

            // 자식 Visual (Sphere placeholder, 1cm)
            var visual = GameObject.CreatePrimitive(PrimitiveType.Sphere);
            visual.name = "Visual";
            visual.transform.SetParent(mosquito.transform, false);
            visual.transform.localScale = new Vector3(0.01f, 0.01f, 0.01f);
            visual.layer = mosquitoLayer;

            // 자식의 자체 SphereCollider 제거 (부모의 Trigger 만 사용)
            var visualCol = visual.GetComponent<SphereCollider>();
            if (visualCol != null) Object.DestroyImmediate(visualCol);

            // Material 검정 (URP)
            var renderer = visual.GetComponent<MeshRenderer>();
            var shader = Shader.Find("Universal Render Pipeline/Lit");
            if (shader == null) shader = Shader.Find("Standard");
            var mat = new Material(shader);
            if (mat.HasProperty("_BaseColor")) mat.SetColor("_BaseColor", Color.black);
            else mat.color = Color.black;
            renderer.sharedMaterial = mat;

            // Prefabs 폴더 생성
            if (!AssetDatabase.IsValidFolder("Assets/Prefabs"))
            {
                AssetDatabase.CreateFolder("Assets", "Prefabs");
            }

            // 기존 prefab 있으면 덮어쓰기
            var prefab = PrefabUtility.SaveAsPrefabAsset(mosquito, PrefabPath);
            Object.DestroyImmediate(mosquito);

            AssetDatabase.SaveAssets();
            AssetDatabase.Refresh();

            Debug.Log($"[GenerateMosquito] {PrefabPath} 생성 완료. MosquitoSpawner 의 Mosquito Prefab 슬롯에 드래그하세요.");
            EditorUtility.FocusProjectWindow();
            Selection.activeObject = prefab;
        }
    }
}
