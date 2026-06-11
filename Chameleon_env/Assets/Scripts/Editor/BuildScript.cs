using UnityEditor;
using UnityEditor.Build.Reporting;
using UnityEngine;

namespace ChameleonRL.EditorTools
{
    /// <summary>
    /// CLI 빌드:
    /// Unity.exe -batchmode -quit -projectPath Chameleon_env -executeMethod ChameleonRL.EditorTools.BuildScript.BuildWindows
    /// </summary>
    public static class BuildScript
    {
        public static void BuildWindows()
        {
            var options = new BuildPlayerOptions
            {
                scenes = new[] { "Assets/Scenes/MainEnv.unity" },
                locationPathName = "../Builds/MainEnv/Chameleon_env.exe",
                target = BuildTarget.StandaloneWindows64,
                options = BuildOptions.None,
            };

            BuildReport report = BuildPipeline.BuildPlayer(options);
            Debug.Log($"[BuildScript] result={report.summary.result} errors={report.summary.totalErrors} size={report.summary.totalSize}");
            if (report.summary.result != BuildResult.Succeeded)
            {
                EditorApplication.Exit(1);
            }
        }
    }
}
