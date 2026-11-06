using System;
using System.IO;
using UnityEditor;
using UnityEditor.Build.Reporting;
using UnityEngine;

namespace V5.EditorTools
{
    public static class V5Build
    {
        public static void BuildWindows()
        {
            string projectRoot = Directory.GetParent(Application.dataPath).FullName;
            string outputDir = Path.Combine(projectRoot, "..", "builds", "v5-windows");
            outputDir = Path.GetFullPath(outputDir);
            Directory.CreateDirectory(outputDir);
            string output = Path.Combine(outputDir, "JungleMonkey.exe");

            var options = new BuildPlayerOptions
            {
                scenes = new[] { "Assets/V5/Scenes/JungleMonkey.unity" },
                locationPathName = output,
                target = BuildTarget.StandaloneWindows64,
                options = BuildOptions.None,
            };
            BuildReport report = BuildPipeline.BuildPlayer(options);
            var summary = report.summary;
            string evidence = JsonUtility.ToJson(new BuildEvidence
            {
                result = summary.result.ToString(),
                totalErrors = summary.totalErrors,
                totalWarnings = summary.totalWarnings,
                outputPath = output,
                totalSize = summary.totalSize,
                buildTimeSeconds = (float)summary.totalTime.TotalSeconds,
                platform = summary.platform.ToString(),
            }, true);
            File.WriteAllText(Path.Combine(projectRoot, "..", "builds", "v5-build.json"),
                evidence);
            Debug.Log("V5_BUILD_RESULT " + evidence);
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
        }
    }
}
