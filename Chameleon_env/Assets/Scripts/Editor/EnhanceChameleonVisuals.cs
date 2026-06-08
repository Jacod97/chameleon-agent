using UnityEditor;
using UnityEngine;

namespace ChameleonRL.EditorTools
{
    /// <summary>
    /// Chameleon 의 시각 메시를 절차적으로 디테일하게 업그레이드.
    /// 구조(HeadPivot, HeadPitchPivot, HeadCamera, TongueMuzzle, Rigidbody, Capsule Collider) 는 보존.
    /// 메뉴: Tools > ChameleonRL > Enhance Chameleon Visuals
    /// </summary>
    public static class EnhanceChameleonVisuals
    {
        private const string MenuPath = "Tools/ChameleonRL/Enhance Chameleon Visuals";

        [MenuItem(MenuPath)]
        public static void Enhance()
        {
            var chameleon = GameObject.Find("Chameleon");
            if (chameleon == null)
            {
                Debug.LogError("[Enhance] Hierarchy 에서 'Chameleon' 을 찾지 못함");
                return;
            }

            int chameleonLayer = LayerMask.NameToLayer("Chameleon");
            var shader = Shader.Find("Universal Render Pipeline/Lit") ?? Shader.Find("Standard");

            // 머티리얼
            var dark = MakeMat(shader, new Color(0.18f, 0.18f, 0.20f));   // 어두운 회색 (본체)
            var mid = MakeMat(shader, new Color(0.40f, 0.42f, 0.45f));    // 중간 회색 (디테일)
            var black = MakeMat(shader, new Color(0.04f, 0.04f, 0.04f));  // 거의 검정 (렌즈/바퀴)
            var ledBlue = MakeEmissive(shader, new Color(0.2f, 0.6f, 1.0f), 2.0f);
            var ledGreen = MakeEmissive(shader, new Color(0.2f, 1.0f, 0.4f), 1.5f);

            // 1) 기존 단순 메시 비활성화
            DeactivateChild(chameleon.transform, "Body");
            DeactivateChild(chameleon.transform, "Wheels");
            var hpp = chameleon.transform.Find("HeadPivot/HeadPitchPivot");
            if (hpp != null) DeactivateChild(hpp, "HeadVisual");

            // 2) 차체 enhanced 추가
            ReplaceChild(chameleon.transform, "BodyVisualEnhanced", root =>
            {
                // 메인 디스크
                AddCylinder(root, "MainDisc", new Vector3(0, 0, 0), Vector3.zero,
                    new Vector3(0.28f, 0.05f, 0.28f), dark, chameleonLayer);
                // 상단 dome (낮은 반구)
                AddSphere(root, "Dome", new Vector3(0, 0.05f, 0),
                    new Vector3(0.22f, 0.07f, 0.22f), mid, chameleonLayer);
                // 상태 LED (녹색)
                AddSphere(root, "StatusLED", new Vector3(0.1f, 0.085f, 0.05f),
                    new Vector3(0.016f, 0.016f, 0.016f), ledGreen, chameleonLayer);
                // 안테나
                AddCylinder(root, "Antenna", new Vector3(-0.08f, 0.11f, 0), Vector3.zero,
                    new Vector3(0.005f, 0.04f, 0.005f), dark, chameleonLayer);
                // 안테나 끝 파란 LED
                AddSphere(root, "AntennaTip", new Vector3(-0.08f, 0.15f, 0),
                    new Vector3(0.012f, 0.012f, 0.012f), ledBlue, chameleonLayer);
                // 좌우 바퀴 (검정)
                AddCylinder(root, "WheelL", new Vector3(-0.15f, -0.025f, 0),
                    new Vector3(0, 0, 90), new Vector3(0.05f, 0.022f, 0.05f), black, chameleonLayer);
                AddCylinder(root, "WheelR", new Vector3(0.15f, -0.025f, 0),
                    new Vector3(0, 0, 90), new Vector3(0.05f, 0.022f, 0.05f), black, chameleonLayer);
                // 캐스터 (앞 작은 바퀴)
                AddSphere(root, "CasterFront", new Vector3(0, -0.04f, 0.13f),
                    new Vector3(0.02f, 0.02f, 0.02f), black, chameleonLayer);
            });

            // 3) 머리 enhanced 추가 (HeadPitchPivot 자식)
            if (hpp != null)
            {
                ReplaceChild(hpp, "HeadVisualEnhanced", root =>
                {
                    // 머리 본체
                    AddCube(root, "HeadBody", new Vector3(0, 0, 0),
                        new Vector3(0.08f, 0.06f, 0.1f), dark, chameleonLayer);
                    // 머리 위 작은 돌출 (상단 디테일)
                    AddCube(root, "TopFin", new Vector3(0, 0.04f, -0.02f),
                        new Vector3(0.02f, 0.025f, 0.05f), mid, chameleonLayer);
                    // 카메라 렌즈 하우징
                    AddCylinder(root, "LensHouse", new Vector3(0, 0, 0.055f),
                        new Vector3(90, 0, 0), new Vector3(0.034f, 0.012f, 0.034f), mid, chameleonLayer);
                    // 카메라 렌즈 (검정)
                    AddCylinder(root, "Lens", new Vector3(0, 0, 0.067f),
                        new Vector3(90, 0, 0), new Vector3(0.024f, 0.008f, 0.024f), black, chameleonLayer);
                    // 렌즈 안 파란 발광 (조준점 느낌)
                    AddCylinder(root, "LensCore", new Vector3(0, 0, 0.072f),
                        new Vector3(90, 0, 0), new Vector3(0.01f, 0.005f, 0.01f), ledBlue, chameleonLayer);
                    // 좌·우 눈 LED
                    AddSphere(root, "EyeL", new Vector3(-0.028f, 0.015f, 0.045f),
                        new Vector3(0.012f, 0.012f, 0.012f), ledBlue, chameleonLayer);
                    AddSphere(root, "EyeR", new Vector3(0.028f, 0.015f, 0.045f),
                        new Vector3(0.012f, 0.012f, 0.012f), ledBlue, chameleonLayer);
                });
            }

            Debug.Log("[EnhanceChameleon] 시각 업그레이드 완료. 기존 Body / Wheels / HeadVisual 비활성화 (구조 보존).");
            Selection.activeGameObject = chameleon;
        }

        // ----- helpers -----
        private static void DeactivateChild(Transform parent, string name)
        {
            var t = parent.Find(name);
            if (t != null) t.gameObject.SetActive(false);
        }

        private static void ReplaceChild(Transform parent, string name, System.Action<GameObject> populate)
        {
            var existing = parent.Find(name);
            if (existing != null) Object.DestroyImmediate(existing.gameObject);
            var go = new GameObject(name);
            go.transform.SetParent(parent, false);
            populate(go);
        }

        private static GameObject AddPrimitive(PrimitiveType type, GameObject parent, string name,
            Vector3 localPos, Vector3 localEuler, Vector3 localScale, Material mat, int layer)
        {
            var go = GameObject.CreatePrimitive(type);
            go.name = name;
            go.transform.SetParent(parent.transform, false);
            go.transform.localPosition = localPos;
            go.transform.localEulerAngles = localEuler;
            go.transform.localScale = localScale;
            var col = go.GetComponent<Collider>();
            if (col != null) Object.DestroyImmediate(col);
            var r = go.GetComponent<MeshRenderer>();
            if (r != null) r.sharedMaterial = mat;
            if (layer >= 0) go.layer = layer;
            return go;
        }

        private static GameObject AddCube(GameObject parent, string n, Vector3 p, Vector3 s, Material m, int l)
            => AddPrimitive(PrimitiveType.Cube, parent, n, p, Vector3.zero, s, m, l);

        private static GameObject AddSphere(GameObject parent, string n, Vector3 p, Vector3 s, Material m, int l)
            => AddPrimitive(PrimitiveType.Sphere, parent, n, p, Vector3.zero, s, m, l);

        private static GameObject AddCylinder(GameObject parent, string n, Vector3 p, Vector3 e, Vector3 s, Material m, int l)
            => AddPrimitive(PrimitiveType.Cylinder, parent, n, p, e, s, m, l);

        private static Material MakeMat(Shader shader, Color color)
        {
            var mat = new Material(shader);
            if (mat.HasProperty("_BaseColor")) mat.SetColor("_BaseColor", color);
            else mat.color = color;
            return mat;
        }

        private static Material MakeEmissive(Shader shader, Color color, float intensity)
        {
            var mat = MakeMat(shader, color);
            if (mat.HasProperty("_EmissionColor"))
            {
                mat.SetColor("_EmissionColor", color * intensity);
                mat.EnableKeyword("_EMISSION");
                mat.globalIlluminationFlags = MaterialGlobalIlluminationFlags.RealtimeEmissive;
            }
            return mat;
        }
    }
}
