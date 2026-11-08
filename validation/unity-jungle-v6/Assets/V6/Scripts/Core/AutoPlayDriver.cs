using System;
using System.IO;
using UnityEngine;

namespace V6
{
    /// <summary>
    /// Command-line driven demo/performance harness. Enabled only with
    /// -v6autoplay. It plays the real scene with injected input, captures real
    /// screenshots with ScreenCapture and quits after a bounded run. It is not
    /// used by PlayMode tests and cannot fabricate results.
    /// </summary>
    public class AutoPlayDriver : MonoBehaviour
    {
        private GameManager manager;
        private float startedAt;
        private float maxSeconds = 90f;
        private string captureDirectory;
        private bool started;
        private bool menuCaptured;
        private bool playCaptured;
        private bool pauseCaptured;
        private bool pausedByDemo;
        private bool completionCaptured;
        private bool gameOverCaptured;
        private float pauseStart = -1f;
        private float finishedAt = -1f;
        private float lastStuckCheck;
        private Vector3 lastStuckPosition;
        private float detourUntil;
        private Vector3 detourDirection;
        private float nextJumpTime;

        private void Start()
        {
            manager = GameManager.Instance != null ? GameManager.Instance : FindFirstObjectByType<GameManager>();
            startedAt = Time.unscaledTime;
            maxSeconds = ReadFloatArg("-v6seconds", 90f);
            captureDirectory = ReadStringArg("-v6capture", null);
            lastStuckCheck = startedAt;
            lastStuckPosition = transform.position;
            Debug.Log($"[V6] AutoPlay enabled seconds={maxSeconds} capture={captureDirectory}");
        }

        private void Update()
        {
            if (manager == null || !manager.IsInitialized)
            {
                return;
            }

            float now = Time.unscaledTime;
            float elapsed = now - startedAt;

            if (!menuCaptured && elapsed > 0.8f)
            {
                menuCaptured = true;
                Capture("01-main-menu");
            }

            if (!started && elapsed > 1.5f)
            {
                started = true;
                if (manager.State == GameState.MainMenu)
                {
                    manager.StartGame();
                }
            }

            if (started && !playCaptured && elapsed > 4.0f && manager.State == GameState.Playing)
            {
                playCaptured = true;
                Capture("02-playing");
            }

            if (started && !pauseCaptured && elapsed > 6.0f && manager.State == GameState.Playing)
            {
                pausedByDemo = true;
                pauseStart = now;
                manager.PauseGame();
                Capture("03-paused");
                pauseCaptured = true;
            }

            if (pausedByDemo && now - pauseStart > 0.6f)
            {
                pausedByDemo = false;
                manager.ResumeGame();
            }

            if (manager.State == GameState.LevelCompleted && !completionCaptured)
            {
                completionCaptured = true;
                Capture("04-level-complete");
                finishedAt = now;
            }

            if (manager.State == GameState.GameOver && !gameOverCaptured)
            {
                gameOverCaptured = true;
                Capture("05-game-over");
                finishedAt = now;
            }

            if (manager.State == GameState.Playing && started && !pausedByDemo)
            {
                DrivePlayer(now);
            }

            if (finishedAt > 0f && now - finishedAt > 3.5f)
            {
                Finish();
            }
            else if (elapsed > maxSeconds)
            {
                Debug.LogWarning($"[V6] AutoPlay timeout after {elapsed:F1}s state={manager.State}");
                Capture("99-timeout");
                Finish();
            }
        }

        private void DrivePlayer(float now)
        {
            PlayerMovement player = manager.Player;
            if (player == null)
            {
                return;
            }

            Vector3 target = manager.Level.DestinationPosition;
            Collectible next = NextCollectible(player.transform.position);
            if (next != null)
            {
                target = next.transform.position;
            }

            Vector3 direction = target - player.transform.position;
            direction.y = 0f;
            if (direction.sqrMagnitude < 0.2f)
            {
                direction = manager.Level.DestinationPosition - player.transform.position;
                direction.y = 0f;
            }

            if (now < detourUntil)
            {
                direction = detourDirection;
            }

            bool jump = false;
            if (now >= nextJumpTime && player.IsGrounded)
            {
                jump = true;
                nextJumpTime = now + 4.5f;
            }

            if (now - lastStuckCheck > 0.9f)
            {
                float moved = Vector3.Distance(
                    new Vector3(player.transform.position.x, 0f, player.transform.position.z),
                    new Vector3(lastStuckPosition.x, 0f, lastStuckPosition.z));
                if (moved < 0.45f && direction.sqrMagnitude > 0.5f)
                {
                    detourDirection = Quaternion.Euler(0f, 68f, 0f) * direction.normalized * direction.magnitude;
                    detourUntil = now + 1.1f;
                    jump = true;
                    Debug.Log("[V6] AutoPlay detour");
                }

                lastStuckCheck = now;
                lastStuckPosition = player.transform.position;
            }

            player.SetAutomationInput(direction, true);
            if (jump)
            {
                player.SetTestInput(new Vector2(0f, 1f), true, true);
                player.SetAutomationInput(direction, true);
            }
        }

        private Collectible NextCollectible(Vector3 position)
        {
            Collectible best = null;
            float bestDistance = float.MaxValue;
            var all = manager.Collectibles != null ? manager.Collectibles.Collectibles : null;
            if (all == null)
            {
                return null;
            }

            foreach (Collectible collectible in all)
            {
                if (collectible == null || collectible.Collected || !collectible.gameObject.activeInHierarchy)
                {
                    continue;
                }

                float distance = Vector3.Distance(position, collectible.transform.position);
                // Strongly prefer the next uncollected item in route order.
                if (distance < bestDistance)
                {
                    bestDistance = distance;
                    best = collectible;
                }
            }

            return best;
        }

        private void Capture(string label)
        {
            if (string.IsNullOrEmpty(captureDirectory))
            {
                return;
            }

            try
            {
                Directory.CreateDirectory(captureDirectory);
                string path = Path.Combine(captureDirectory, label + ".png");
                ScreenCapture.CaptureScreenshot(path);
                Debug.Log("[V6] Screenshot requested: " + path);
            }
            catch (Exception exception)
            {
                Debug.LogWarning("[V6] Screenshot failed: " + exception.Message);
            }
        }

        private void Finish()
        {
            manager?.Player?.ClearAutomationInput();
            manager?.Performance?.WriteReport(true);
            Debug.Log("[V6] AutoPlay finished; quitting");
            Application.Quit();
            enabled = false;
        }

        private static string ReadStringArg(string key, string fallback)
        {
            string[] args = Environment.GetCommandLineArgs();
            for (int i = 0; i < args.Length - 1; i++)
            {
                if (args[i] == key)
                {
                    return args[i + 1];
                }
            }

            return fallback;
        }

        private static float ReadFloatArg(string key, float fallback)
        {
            string value = ReadStringArg(key, null);
            return float.TryParse(value, out float parsed) ? parsed : fallback;
        }
    }
}
