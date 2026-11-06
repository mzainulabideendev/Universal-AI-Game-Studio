using System;
using System.Collections;
using System.IO;
using System.Text;
using UnityEngine;

namespace V5
{
    /// <summary>
    /// Optional built-player evidence driver. It only runs when the executable is
    /// started with -v5demo; interactive players are unaffected.
    /// </summary>
    public class V5DemoDriver : MonoBehaviour
    {
        [Serializable]
        private class Evidence
        {
            public bool demoRan;
            public string scene;
            public float startX;
            public float startY;
            public float startZ;
            public float endX;
            public float endY;
            public float endZ;
            public float distanceMoved;
            public float peakY;
            public bool groundedAtEnd;
            public int score;
            public int totalBananas;
            public bool animatorPresent;
            public float animatorSpeed;
            public string screenshot;
            public string error;
        }

        private void Start()
        {
            string[] args = Environment.GetCommandLineArgs();
            if (Array.IndexOf(args, "-v5demo") < 0)
            {
                return;
            }
            StartCoroutine(RunDemo(args));
        }

        private IEnumerator RunDemo(string[] args)
        {
            var evidence = new Evidence
            {
                demoRan = true,
                scene = gameObject.scene.name,
            };

            string shotPath = ArgumentValue(args, "-v5shot");
            string logPath = ArgumentValue(args, "-v5log");

            var controller = FindFirstObjectByType<MonkeyController>();
            var manager = FindFirstObjectByType<GameManager>();
            if (controller == null)
            {
                evidence.error = "MonkeyController not found";
                Write(logPath, evidence);
                Application.Quit(2);
                yield break;
            }

            Vector3 start = controller.transform.position;
            evidence.startX = start.x;
            evidence.startY = start.y;
            evidence.startZ = start.z;

            yield return new WaitForSeconds(0.5f);

            controller.SetTestInput(new Vector2(0f, 1f), false, true);
            float elapsed = 0f;
            float peakY = start.y;
            bool jumped = false;
            while (elapsed < 2.4f)
            {
                elapsed += Time.deltaTime;
                peakY = Mathf.Max(peakY, controller.transform.position.y);
                if (!jumped && elapsed > 0.9f)
                {
                    controller.SetTestInput(new Vector2(0f, 1f), true, true);
                    jumped = true;
                }
                yield return null;
            }

            controller.SetTestInput(Vector2.zero, false, false);
            yield return new WaitForSeconds(0.3f);

            if (!string.IsNullOrEmpty(shotPath))
            {
                ScreenCapture.CaptureScreenshot(shotPath);
                evidence.screenshot = shotPath;
            }
            yield return new WaitForSeconds(0.6f);

            Vector3 end = controller.transform.position;
            evidence.endX = end.x;
            evidence.endY = end.y;
            evidence.endZ = end.z;
            evidence.distanceMoved = Vector3.Distance(start, end);
            evidence.peakY = peakY;
            evidence.groundedAtEnd = controller.IsGrounded;
            evidence.animatorPresent = controller.Animator != null;
            evidence.animatorSpeed = controller.Animator != null
                ? controller.Animator.GetFloat("Speed")
                : 0f;
            if (manager != null)
            {
                evidence.score = manager.Score;
                evidence.totalBananas = manager.TotalBananas;
            }

            Write(logPath, evidence);
            yield return new WaitForSeconds(0.2f);
            Application.Quit(0);
        }

        private static string ArgumentValue(string[] args, string key)
        {
            int index = Array.IndexOf(args, key);
            if (index >= 0 && index + 1 < args.Length)
            {
                return args[index + 1];
            }
            return null;
        }

        private static void Write(string path, Evidence evidence)
        {
            if (string.IsNullOrEmpty(path))
            {
                return;
            }
            var builder = new StringBuilder();
            builder.Append("{");
            builder.Append($"\"demoRan\":{Bool(evidence.demoRan)},");
            builder.Append($"\"scene\":\"{Escape(evidence.scene)}\",");
            builder.Append($"\"start\":[{evidence.startX:F3},{evidence.startY:F3},{evidence.startZ:F3}],");
            builder.Append($"\"end\":[{evidence.endX:F3},{evidence.endY:F3},{evidence.endZ:F3}],");
            builder.Append($"\"distanceMoved\":{evidence.distanceMoved:F3},");
            builder.Append($"\"peakY\":{evidence.peakY:F3},");
            builder.Append($"\"groundedAtEnd\":{Bool(evidence.groundedAtEnd)},");
            builder.Append($"\"score\":{evidence.score},");
            builder.Append($"\"totalBananas\":{evidence.totalBananas},");
            builder.Append($"\"animatorPresent\":{Bool(evidence.animatorPresent)},");
            builder.Append($"\"animatorSpeed\":{evidence.animatorSpeed:F3},");
            builder.Append($"\"screenshot\":\"{Escape(evidence.screenshot)}\",");
            builder.Append($"\"error\":\"{Escape(evidence.error)}\"");
            builder.Append("}");
            File.WriteAllText(path, builder.ToString());
        }

        private static string Bool(bool value) => value ? "true" : "false";

        private static string Escape(string value) =>
            (value ?? string.Empty).Replace("\\", "\\\\").Replace("\"", "\\\"");
    }
}
