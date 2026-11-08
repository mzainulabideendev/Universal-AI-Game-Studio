using System;
using System.Collections.Generic;
using UnityEngine;

namespace V6
{
    [Serializable]
    public class SceneValidationReport
    {
        public bool passed;
        public string[] issues;
        public int collectibles;
        public bool playerGrounded;
        public string state;
        public bool animatorPresent;
        public bool environmentPresent;
        public bool destinationPresent;
        public bool cameraPresent;
        public bool uiPresent;
        public string spawn;
        public string destination;
    }

    /// <summary>
    /// Deterministic startup/validation entry point. Initializes the manager
    /// before any gameplay frame, validates every required scene reference and
    /// reports honest problems instead of letting a half-built scene run.
    /// </summary>
    public class GameBootstrap : MonoBehaviour
    {
        [SerializeField] private GameManager gameManager;
        [SerializeField] private GameObject environment;
        [SerializeField] private string sceneVersion = "v6-phase5";

        public GameManager Manager => gameManager;
        public SceneValidationReport LastReport { get; private set; }
        public bool Initialized { get; private set; }

        public void Configure(GameManager manager, GameObject environmentRoot)
        {
            gameManager = manager;
            environment = environmentRoot;
        }

        private void Awake()
        {
            GameplayEventBus.Reset();
            Application.targetFrameRate = 60;
            QualitySettings.vSyncCount = 0;

            if (gameManager == null)
            {
                gameManager = FindFirstObjectByType<GameManager>();
            }

            if (HasArgument("-v6autoplay"))
            {
                gameObject.AddComponent<AutoPlayDriver>();
            }
        }

        private void Start()
        {
            if (gameManager == null)
            {
                Debug.LogError("[V6] GameBootstrap has no GameManager");
                return;
            }

            gameManager.Initialize();
            Initialized = gameManager.IsInitialized;
            LastReport = BuildReport();
            string json = JsonUtility.ToJson(LastReport);
            if (LastReport.passed)
            {
                Debug.Log("V6_SCENE_VALID " + json);
            }
            else
            {
                Debug.LogError("V6_SCENE_INVALID " + json);
            }
        }

        public SceneValidationReport ValidateScene()
        {
            LastReport = BuildReport();
            return LastReport;
        }

        private SceneValidationReport BuildReport()
        {
            var issues = new List<string>();
            bool animator = false;
            bool playerGrounded = false;
            int collectibles = 0;
            bool destination = false;
            bool camera = false;
            bool ui = false;
            bool environmentPresent = environment != null && environment.activeInHierarchy;
            string spawn = "none";
            string destinationText = "none";
            string state = "none";

            if (gameManager == null)
            {
                issues.Add("GameManager missing");
            }
            else
            {
                if (!gameManager.IsInitialized)
                {
                    issues.Add("GameManager not initialized");
                }

                state = gameManager.State.ToString();
                if (gameManager.Player == null)
                {
                    issues.Add("PlayerMovement missing");
                }
                else
                {
                    playerGrounded = gameManager.Player.IsGrounded;
                    animator = gameManager.Player.GetComponentInChildren<Animator>() != null;
                    if (!animator)
                    {
                        issues.Add("Animator missing on player");
                    }
                }

                if (gameManager.Collectibles == null)
                {
                    issues.Add("CollectibleManager missing");
                }
                else
                {
                    collectibles = gameManager.Collectibles.Total;
                    if (collectibles < 10)
                    {
                        issues.Add($"Only {collectibles} collectibles (need >= 10)");
                    }

                    var placement = gameManager.Collectibles.ValidatePlacement();
                    if (!placement.Passed)
                    {
                        issues.Add("Collectible placement validation failed: " +
                                   string.Join("; ", placement.Problems));
                    }
                }

                if (gameManager.Level == null)
                {
                    issues.Add("LevelManager missing");
                }
                else
                {
                    spawn = gameManager.Level.SpawnPosition.ToString("F2");
                    if (!gameManager.Level.HasGroundBelow(gameManager.Level.SpawnPosition, 5f))
                    {
                        issues.Add("No ground below spawn");
                    }
                }

                if (gameManager.Destination == null)
                {
                    issues.Add("DestinationZone missing");
                }
                else
                {
                    destination = true;
                    destinationText = gameManager.Destination.transform.position.ToString("F2");
                }

                if (gameManager.FollowCamera == null)
                {
                    issues.Add("CameraFollowController missing");
                }
                else
                {
                    camera = true;
                }

                if (gameManager.UI == null)
                {
                    issues.Add("UIManager missing");
                }
                else
                {
                    ui = gameManager.UI.Initialized;
                    if (!ui)
                    {
                        issues.Add("UIManager not initialized");
                    }
                }

                if (gameManager.Save == null) issues.Add("SaveDataService missing");
                if (gameManager.Audio == null) issues.Add("AudioManager missing");
                if (gameManager.Performance == null) issues.Add("PerformanceMonitor missing");
                if (gameManager.Score == null) issues.Add("ScoreManager missing");
                if (gameManager.Objectives == null) issues.Add("ObjectiveManager missing");
            }

            if (!environmentPresent)
            {
                issues.Add("Environment root missing/inactive");
            }

            return new SceneValidationReport
            {
                passed = issues.Count == 0,
                issues = issues.ToArray(),
                collectibles = collectibles,
                playerGrounded = playerGrounded,
                state = state,
                animatorPresent = animator,
                environmentPresent = environmentPresent,
                destinationPresent = destination,
                cameraPresent = camera,
                uiPresent = ui,
                spawn = spawn,
                destination = destinationText,
            };
        }

        private static bool HasArgument(string value)
        {
            string[] args = Environment.GetCommandLineArgs();
            for (int i = 0; i < args.Length; i++)
            {
                if (args[i] == value)
                {
                    return true;
                }
            }

            return false;
        }

        public string SceneVersion => sceneVersion;
    }
}
