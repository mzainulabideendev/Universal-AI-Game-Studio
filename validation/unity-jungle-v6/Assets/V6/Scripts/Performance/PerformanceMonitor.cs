using System;
using System.Collections.Generic;
using System.IO;
using Unity.Profiling;
using UnityEngine;

namespace V6
{
    [Serializable]
    public class PerformanceSnapshot
    {
        public int frames;
        public float durationSeconds;
        public float averageFps;
        public float minimumFps;
        public float onePercentLowFps;
        public float averageFrameMs;
        public float p95FrameMs;
        public float maxFrameMs;
        public long managedMemoryBytes;
        public long totalAllocatedMemoryBytes;
        public long gcAllocatedBytes;
        public int activeGameObjects;
        public int activeRenderers;
        public int activeTriangles;
        public int drawCalls;
        public int screenWidth;
        public int screenHeight;
        public string qualityLevel;
        public float physicsStepMs;
        public string capturedUtc;
    }

    /// <summary>
    /// Real frame-time and scene-cost sampling. Reports only what it actually
    /// measured; draw calls are -1 when the platform recorder is unavailable.
    /// </summary>
    public class PerformanceMonitor : MonoBehaviour
    {
        [SerializeField] private float summaryIntervalSeconds = 5f;
        [SerializeField] private int frameSampleCapacity = 4096;

        private readonly List<float> frameTimes = new List<float>(4096);
        private ProfilerRecorder drawCallsRecorder;
        private int drawCalls = -1;
        private int activeGameObjects;
        private int activeRenderers;
        private int activeTriangles;
        private long allocatedMemory;
        private float lastSummaryTime;
        private int totalFrames;
        private float totalDuration;
        private string reportPath;
        private bool wroteFinal;

        public PerformanceSnapshot LastSnapshot { get; private set; } = new PerformanceSnapshot();
        public string ReportPath => reportPath;

        public void Initialize()
        {
            string[] args = Environment.GetCommandLineArgs();
            for (int i = 0; i < args.Length - 1; i++)
            {
                if (args[i] == "-v6perf")
                {
                    reportPath = args[i + 1];
                }
            }

            try
            {
                drawCallsRecorder = ProfilerRecorder.StartNew(ProfilerCategory.Render, "Draw Calls Count");
            }
            catch (Exception exception)
            {
                Debug.LogWarning("[V6] Draw call recorder unavailable: " + exception.Message);
            }

            lastSummaryTime = Time.unscaledTime;
            LastSnapshot = CaptureMetrics(0f);
        }

        public PerformanceSnapshot GetSnapshot() => LastSnapshot;

        private void Update()
        {
            float dt = Time.unscaledDeltaTime;
            if (dt <= 0f)
            {
                return;
            }

            totalFrames++;
            totalDuration += dt;
            frameTimes.Add(dt);
            if (frameTimes.Count > frameSampleCapacity)
            {
                frameTimes.RemoveAt(0);
            }

            if (Time.unscaledTime - lastSummaryTime >= summaryIntervalSeconds)
            {
                lastSummaryTime = Time.unscaledTime;
                LastSnapshot = CaptureMetrics(dt);
                if (!string.IsNullOrEmpty(reportPath))
                {
                    WriteReport(false);
                }
            }
        }

        public PerformanceSnapshot CaptureMetrics(float latestFrame)
        {
            frameTimes.Sort();
            int count = frameTimes.Count;
            float avgMs = 0f;
            float maxMs = 0f;
            float p95 = 0f;
            float onePercentLow = 0f;
            if (count > 0)
            {
                float sum = 0f;
                for (int i = 0; i < count; i++)
                {
                    sum += frameTimes[i];
                }

                avgMs = sum * 1000f / count;
                maxMs = frameTimes[count - 1] * 1000f;
                int p95Index = Mathf.Clamp(Mathf.RoundToInt(count * 0.95f) - 1, 0, count - 1);
                p95 = frameTimes[p95Index] * 1000f;

                int worstCount = Mathf.Max(1, Mathf.CeilToInt(count * 0.01f));
                float worstSum = 0f;
                for (int i = count - worstCount; i < count; i++)
                {
                    worstSum += frameTimes[i];
                }

                onePercentLow = worstCount > 0 ? worstSum / worstCount * 1000f : maxMs;
            }

            RefreshSceneMetrics();

            return new PerformanceSnapshot
            {
                frames = totalFrames,
                durationSeconds = totalDuration,
                averageFps = totalDuration > 0f ? totalFrames / totalDuration : 0f,
                minimumFps = maxMs > 0f ? 1000f / maxMs : 0f,
                onePercentLowFps = onePercentLow > 0f ? 1000f / onePercentLow : 0f,
                averageFrameMs = avgMs,
                p95FrameMs = p95,
                maxFrameMs = maxMs,
                managedMemoryBytes = GC.GetTotalMemory(false),
                totalAllocatedMemoryBytes = allocatedMemory,
                gcAllocatedBytes = 0,
                activeGameObjects = activeGameObjects,
                activeRenderers = activeRenderers,
                activeTriangles = activeTriangles,
                drawCalls = drawCalls,
                screenWidth = Screen.width,
                screenHeight = Screen.height,
                qualityLevel = QualitySettings.names.Length > 0
                    ? QualitySettings.names[QualitySettings.GetQualityLevel()]
                    : "unknown",
                physicsStepMs = Time.fixedDeltaTime * 1000f,
                capturedUtc = DateTime.UtcNow.ToString("o"),
            };
        }

        private void RefreshSceneMetrics()
        {
            if (drawCallsRecorder.Valid)
            {
                drawCalls = (int)drawCallsRecorder.LastValue;
            }

            try
            {
                allocatedMemory = UnityEngine.Profiling.Profiler.GetTotalAllocatedMemoryLong();
            }
            catch
            {
                allocatedMemory = -1;
            }

            GameObject[] objects = FindObjectsByType<GameObject>(FindObjectsSortMode.None);
            activeGameObjects = 0;
            activeRenderers = 0;
            activeTriangles = 0;
            foreach (GameObject go in objects)
            {
                if (!go.activeInHierarchy)
                {
                    continue;
                }

                activeGameObjects++;
                var renderer = go.GetComponent<Renderer>();
                if (renderer == null || !renderer.enabled)
                {
                    continue;
                }

                activeRenderers++;
                var filter = go.GetComponent<MeshFilter>();
                if (filter != null && filter.sharedMesh != null)
                {
                    activeTriangles += filter.sharedMesh.triangles.Length / 3;
                }
            }
        }

        public bool WriteReport(bool final)
        {
            if (string.IsNullOrEmpty(reportPath))
            {
                return false;
            }

            if (final)
            {
                if (wroteFinal)
                {
                    return true;
                }

                LastSnapshot = CaptureMetrics(0f);
                wroteFinal = true;
            }

            try
            {
                string directory = Path.GetDirectoryName(reportPath);
                if (!string.IsNullOrEmpty(directory))
                {
                    Directory.CreateDirectory(directory);
                }

                File.WriteAllText(reportPath, JsonUtility.ToJson(LastSnapshot, true));
                Debug.Log("V6_PERF " + JsonUtility.ToJson(LastSnapshot));
                return true;
            }
            catch (Exception exception)
            {
                Debug.LogError("[V6] Failed to write performance report: " + exception.Message);
                return false;
            }
        }

        private void OnApplicationQuit()
        {
            WriteReport(true);
        }

        private void OnDestroy()
        {
            if (drawCallsRecorder.Valid)
            {
                drawCallsRecorder.Dispose();
            }
        }
    }
}
