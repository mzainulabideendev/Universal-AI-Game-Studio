using System;
using System.IO;
using UnityEditor;
using UnityEditor.Build.Reporting;
using UnityEngine;

namespace V6.EditorTools
{
    /// <summary>
    /// Windows Standalone build entry point. Invoked from batchmode with
    /// -executeMethod V6.EditorTools.V6Build.BuildWindows.
    /// </summary>
    public static class V6Build
    {
        public static void BuildWindows()
        {
            string projectRoot = Directory.GetParent(Application.dataPath).FullName;
            string outputDir = Path.GetFullPath(Path.Combine(projectRoot, "..", "builds", "v6-windows"));
            Directory.CreateDirectory(outputDir);
            string output = Path.Combine(outputDir, "V6JungleMonkey.exe");

            string[] scenes = new[] { "Assets/V6/Scenes/JungleMonkeyV6.unity" };
            var options = new BuildPlayerOptions
            {
                scenes = scenes,
                locationPathName = output,
                target = BuildTarget.StandaloneWindows64,
                options = BuildOptions.None,
            };

            BuildReport report = BuildPipeline.BuildPlayer(options);
            BuildSummary summary = report.summary;
            var evidence = new BuildEvidence
            {
                result = summary.result.ToString(),
                totalErrors = summary.totalErrors,
                totalWarnings = summary.totalWarnings,
                outputPath = output,
                totalSize = summary.totalSize,
                buildTimeSeconds = (float)summary.totalTime.TotalSeconds,
                platform = summary.platform.ToString(),
                unityVersion = Application.unityVersion,
            };

            string reportDir = Path.GetFullPath(Path.Combine(projectRoot, "..", "..", "reports"));
            Directory.CreateDirectory(reportDir);
            string json = JsonUtility.ToJson(evidence, true);
            File.WriteAllText(Path.Combine(reportDir, "v6-build-raw.json"), json);
            Debug.Log("V6_BUILD_RESULT " + JsonUtility.ToJson(evidence));

            if (summary.result != BuildResult.Succeeded)
            {
                throw new InvalidOperationException("Unity build failed: " + summary.result);
            }
        }

        [Serializable]
        private class BuildEvidence
        {
            public string result;
            public int totalErrors;
            public int totalWarnings;
            public string outputPath;
            public ulong totalSize;
            public float buildTimeSeconds;
            public string platform;
            public string unityVersion;
        }
    }
}
