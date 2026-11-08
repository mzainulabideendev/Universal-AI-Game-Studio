using UnityEngine;

namespace V6
{
    /// <summary>
    /// Central gameplay orchestrator. Owns legal state changes, time scale,
    /// score/objective flow, pause/restart/completion, save data and input
    /// gating. Gameplay events are ignored unless the state is Playing.
    /// </summary>
    public class GameManager : MonoBehaviour
    {
        public static GameManager Instance { get; private set; }

        [Header("Systems")]
        public GameStateController States;
        public PlayerInputHandler InputHandler;
        public PlayerMovement Player;
        public PlayerAnimationDriver AnimationDriver;
        public PlayerCollisionHandler CollisionHandler;
        public CameraFollowController FollowCamera;
        public CollectibleManager Collectibles;
        public ScoreManager Score;
        public ObjectiveManager Objectives;
        public LevelManager Level;
        public CheckpointManager Checkpoints;
        public DestinationZone Destination;
        public UIManager UI;
        public AudioManager Audio;
        public SaveDataService Save;
        public PerformanceMonitor Performance;

        [Header("Tuning")]
        [SerializeField] private float menuToastSeconds = 3f;

        private bool initialized;
        private bool savedOnQuit;

        public bool IsInitialized => initialized;
        public GameState State => States != null ? States.Current : GameState.Initializing;
        public int ScoreValue => Score != null ? Score.Score : 0;
        public int BestScore => Score != null ? Score.BestScore : 0;
        public int TotalBananas => Collectibles != null ? Collectibles.Total : 0;
        public int CollectedBananas => Collectibles != null ? Collectibles.CollectedCount : 0;
        public SaveData SaveData { get; private set; }
        public string LastGameOverReason { get; private set; } = string.Empty;

        private void Awake()
        {
            Instance = this;
            ResolveReferences();
            Time.timeScale = 1f;
        }

        private void Start()
        {
            Initialize();
        }

        private void ResolveReferences()
        {
            if (States == null) States = GetComponent<GameStateController>();
            if (InputHandler == null) InputHandler = FindFirstObjectByType<PlayerInputHandler>();
            if (Player == null) Player = FindFirstObjectByType<PlayerMovement>();
            if (AnimationDriver == null) AnimationDriver = FindFirstObjectByType<PlayerAnimationDriver>();
            if (CollisionHandler == null) CollisionHandler = FindFirstObjectByType<PlayerCollisionHandler>();
            if (FollowCamera == null) FollowCamera = FindFirstObjectByType<CameraFollowController>();
            if (Collectibles == null) Collectibles = FindFirstObjectByType<CollectibleManager>();
            if (Score == null) Score = GetComponent<ScoreManager>();
            if (Objectives == null) Objectives = GetComponent<ObjectiveManager>();
            if (Level == null) Level = FindFirstObjectByType<LevelManager>();
            if (Checkpoints == null) Checkpoints = FindFirstObjectByType<CheckpointManager>();
            if (Destination == null) Destination = FindFirstObjectByType<DestinationZone>();
            if (UI == null) UI = FindFirstObjectByType<UIManager>();
            if (Audio == null) Audio = GetComponent<AudioManager>();
            if (Save == null) Save = GetComponent<SaveDataService>();
            if (Performance == null) Performance = GetComponent<PerformanceMonitor>();
        }

        public void Initialize()
        {
            if (initialized)
            {
                return;
            }

            ResolveReferences();
            if (!ValidateSystems())
            {
                enabled = false;
                return;
            }

            SaveData = Save.Load();
            Score.Initialize(SaveData.bestScore);
            Audio.Initialize();
            ApplySettings();

            Level.Initialize();
            Player.Initialize(InputHandler, States, Level, this, FollowCamera.transform);
            CollisionHandler.Initialize(this);
            Collectibles.Initialize(Level, Player.transform, States, Audio);
            Checkpoints.Initialize(Level);
            Destination.Initialize(this, Player.transform);
            Objectives.Configure(Collectibles.Total, true);
            Objectives.ResetObjectives();
            FollowCamera.Initialize(Player.transform, InputHandler);
            AnimationDriver.Initialize(Player, States);
            Performance.Initialize();
            UI.Initialize(this);

            Collectibles.Collected += OnBananaCollected;
            Objectives.ProgressChanged += OnObjectiveProgress;
            States.StateChanged += OnStateChanged;

            UI.SetScore(0, TotalBananas);
            UI.SetObjective(Objectives.ProgressLabel());
            UI.SetBest(Score.BestScore);

            Player.Teleport(Level.SpawnPosition);
            FaceDestination();
            FollowCamera.Snap();

            initialized = true;
            States.ResetTo(GameState.Initializing);
            States.TryTransition(GameState.MainMenu);
            Debug.Log($"[V6] GameManager initialized bananas={TotalBananas} " +
                      $"spawn={Level.SpawnPosition:F2} save={Save.LastStatus}");
        }

        private bool ValidateSystems()
        {
            string missing = string.Empty;
            if (States == null) missing += "States ";
            if (InputHandler == null) missing += "Input ";
            if (Player == null) missing += "Player ";
            if (AnimationDriver == null) missing += "Animation ";
            if (CollisionHandler == null) missing += "Collision ";
            if (FollowCamera == null) missing += "Camera ";
            if (Collectibles == null) missing += "Collectibles ";
            if (Score == null) missing += "Score ";
            if (Objectives == null) missing += "Objectives ";
            if (Level == null) missing += "Level ";
            if (Checkpoints == null) missing += "Checkpoints ";
            if (Destination == null) missing += "Destination ";
            if (UI == null) missing += "UI ";
            if (Audio == null) missing += "Audio ";
            if (Save == null) missing += "Save ";
            if (Performance == null) missing += "Performance ";
            if (!string.IsNullOrEmpty(missing))
            {
                Debug.LogError("[V6] Missing gameplay systems: " + missing);
                return false;
            }

            return true;
        }

        private void Update()
        {
            if (!initialized || InputHandler == null)
            {
                return;
            }

            switch (States.Current)
            {
                case GameState.MainMenu:
                    if (InputHandler.StartPressed)
                    {
                        StartGame();
                    }
                    break;
                case GameState.Playing:
                    if (InputHandler.PausePressed)
                    {
                        PauseGame();
                    }
                    else if (InputHandler.RestartPressed)
                    {
                        RestartGame();
                    }
                    break;
                case GameState.Paused:
                    if (InputHandler.PausePressed)
                    {
                        ResumeGame();
                    }
                    else if (InputHandler.RestartPressed)
                    {
                        RestartGame();
                    }
                    break;
                case GameState.GameOver:
                case GameState.LevelCompleted:
                    if (InputHandler.RestartPressed)
                    {
                        RestartGame();
                    }
                    else if (InputHandler.PausePressed)
                    {
                        ReturnToMainMenu();
                    }
                    break;
            }
        }

        public void StartGame()
        {
            if (!initialized || States.Current != GameState.MainMenu)
            {
                return;
            }

            ResetGameplay();
            if (States.TryTransition(GameState.Playing))
            {
                UI.ShowToast("Collect 10 bananas, then reach the jungle ruins", menuToastSeconds);
            }
        }

        public void PauseGame()
        {
            if (!initialized || !States.IsPlaying)
            {
                return;
            }

            if (States.TryTransition(GameState.Paused))
            {
                Audio.PlayPause();
            }
        }

        public void ResumeGame()
        {
            if (!initialized || !States.IsPaused)
            {
                return;
            }

            States.TryTransition(GameState.Playing);
            Audio.PlayPause();
        }

        public void RestartGame()
        {
            if (!initialized)
            {
                return;
            }

            if (States.Current == GameState.MainMenu)
            {
                StartGame();
                return;
            }

            if (!States.TryTransition(GameState.Restarting))
            {
                return;
            }

            Time.timeScale = 1f;
            ResetGameplay();
            States.TryTransition(GameState.Playing);
            UI.ShowToast("Run restarted", 1.6f);
        }

        public void ReturnToMainMenu()
        {
            if (!initialized || States.Current == GameState.MainMenu)
            {
                return;
            }

            if (!States.TryTransition(GameState.MainMenu))
            {
                return;
            }

            Time.timeScale = 1f;
            ResetGameplay();
            SaveProgress();
        }

        public void TriggerGameOver(string reason)
        {
            if (!initialized || !States.IsPlaying)
            {
                return;
            }

            LastGameOverReason = reason;
            if (States.TryTransition(GameState.GameOver))
            {
                SaveData.totalRuns++;
                Score.SubmitToBest();
                SaveData.bestScore = Score.BestScore;
                SaveProgress();
                UI.SetGameOverReason(reason);
                UI.SetBest(Score.BestScore);
                Audio.PlayGameOver();
            }
        }

        public void CompleteLevel()
        {
            if (!initialized || !States.IsPlaying)
            {
                return;
            }

            if (!States.TryTransition(GameState.LevelCompleted))
            {
                return;
            }

            bool newBest = Score.SubmitToBest();
            SaveData.bestScore = Score.BestScore;
            SaveData.jungleLevelCompleted = true;
            SaveData.totalRuns++;
            SaveData.totalBananasCollected += CollectedBananas;
            SaveProgress();
            UI.SetBest(Score.BestScore);
            UI.SetCompletionStats(ScoreValue, TotalBananas, Score.BestScore, newBest);
            Audio.PlayComplete();
            GameplayEventBus.RaiseLevelCompleted();
        }

        public void OnBananaCollected(Collectible collectible)
        {
            if (!States.IsGameplayActive || collectible == null)
            {
                return;
            }

            Score.Add(collectible.Value);
            Objectives.RegisterBanana();
            UI.SetScore(Score.Score, TotalBananas);
            UI.SetObjective(Objectives.ProgressLabel());
            Audio.PlayCollect();

            if (Objectives.IsComplete)
            {
                CompleteLevel();
            }
            else if (Objectives.CollectedBananas >= Objectives.TargetBananas)
            {
                UI.ShowToast("All bananas collected! Reach the ruins", 2.6f);
            }
        }

        public void OnDestinationReached()
        {
            if (!States.IsGameplayActive)
            {
                return;
            }

            bool complete = Objectives.MarkDestinationReached();
            UI.SetObjective(Objectives.ProgressLabel());
            if (complete)
            {
                CompleteLevel();
                return;
            }

            int remaining = Mathf.Max(0, Objectives.TargetBananas - Objectives.CollectedBananas);
            UI.ShowToast($"The ruins are near - {remaining} bananas still hidden", 2.6f);
        }

        public void OnPlayerFell()
        {
            if (!States.IsGameplayActive)
            {
                return;
            }

            Vector3 respawn = Checkpoints != null ? Checkpoints.RespawnPosition : Level.SpawnPosition;
            Player.Teleport(respawn);
            Player.ResetVelocity();
            Player.SetFacing(Level.DestinationPosition - respawn);
            FollowCamera.Snap();
            UI.ShowToast("You fell - returned to the last checkpoint", 2.2f);
        }

        public void OnPlayerEnteredHazard(string hazardName)
        {
            if (!States.IsGameplayActive)
            {
                return;
            }

            TriggerGameOver("The river swept the monkey away.\nPress R to restart.");
        }

        public void OnPlayerLanded()
        {
            if (!States.IsGameplayActive)
            {
                return;
            }

            Audio.PlayLand();
        }

        private void OnObjectiveProgress(int current, int target)
        {
            GameplayEventBus.RaiseObjectiveProgress(current, target);
        }

        private void OnStateChanged(GameState previous, GameState next)
        {
            GameplayEventBus.RaiseStateChanged(previous, next);
            if (UI != null)
            {
                UI.ShowState(next);
            }

            switch (next)
            {
                case GameState.Playing:
                    Time.timeScale = 1f;
                    InputHandler.LookEnabled = true;
                    SetCursorLocked(true);
                    break;
                case GameState.Paused:
                case GameState.GameOver:
                case GameState.LevelCompleted:
                    Time.timeScale = 0f;
                    InputHandler.LookEnabled = false;
                    SetCursorLocked(false);
                    break;
                case GameState.MainMenu:
                case GameState.Restarting:
                    Time.timeScale = next == GameState.Restarting ? Time.timeScale : 1f;
                    InputHandler.LookEnabled = false;
                    SetCursorLocked(false);
                    break;
            }
        }

        public void ResetGameplay()
        {
            Score.ResetScore();
            Objectives.ResetObjectives();
            Collectibles.ResetAll();
            Checkpoints.ResetCheckpoints();
            Destination.ResetZone();
            UI.ClearToast();
            UI.SetScore(0, TotalBananas);
            UI.SetObjective(Objectives.ProgressLabel());
            UI.SetBest(Score.BestScore);

            Player.Teleport(Level.SpawnPosition);
            Player.ResetVelocity();
            FaceDestination();
            FollowCamera.Snap();
        }

        private void FaceDestination()
        {
            Vector3 direction = Level.DestinationPosition - Player.transform.position;
            direction.y = 0f;
            if (direction.sqrMagnitude > 0.01f)
            {
                Player.SetFacing(direction);
            }
        }

        private void ApplySettings()
        {
            if (SaveData == null)
            {
                return;
            }

            InputHandler.LookSensitivity = 2.2f * SaveData.mouseSensitivity;
            FollowCamera.SetSensitivity(2.2f * SaveData.mouseSensitivity);
            Audio.SetMasterVolume(SaveData.masterVolume);
        }

        private void SaveProgress()
        {
            if (Save == null || SaveData == null)
            {
                return;
            }

            SaveData.bestScore = Mathf.Max(SaveData.bestScore, Score != null ? Score.BestScore : 0);
            Save.Save(SaveData);
        }

        private void SetCursorLocked(bool locked)
        {
            if (Application.isEditor)
            {
                return;
            }

            Cursor.lockState = locked ? CursorLockMode.Locked : CursorLockMode.None;
            Cursor.visible = !locked;
        }

        private void OnApplicationQuit()
        {
            if (!initialized || savedOnQuit)
            {
                return;
            }

            savedOnQuit = true;
            SaveProgress();
            Performance?.WriteReport(true);
        }

        private void OnDestroy()
        {
            if (Instance == this)
            {
                Instance = null;
            }
        }
    }
}
