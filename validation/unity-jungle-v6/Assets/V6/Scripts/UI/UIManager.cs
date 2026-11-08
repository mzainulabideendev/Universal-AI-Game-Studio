using System.Collections;
using UnityEngine;
using UnityEngine.UI;

namespace V6
{
    /// <summary>
    /// All gameplay UI: HUD, main menu, pause, game over and completion.
    /// Every visible control is wired to a real <see cref="GameManager"/>
    /// method; there are no decorative buttons.
    /// </summary>
    public class UIManager : MonoBehaviour
    {
        [Header("Panels")]
        public GameObject hudGroup;
        public GameObject mainMenuPanel;
        public GameObject pausePanel;
        public GameObject gameOverPanel;
        public GameObject completePanel;

        [Header("HUD")]
        public Text bananaText;
        public Text objectiveText;
        public Text bestText;
        public Text helpText;
        public Text toastText;

        [Header("Main menu")]
        public Text mainMenuBestText;
        public Button startButton;

        [Header("Pause")]
        public Button pauseButton;
        public Button restartButton;
        public Button resumeButton;
        public Button pauseRestartButton;
        public Button pauseMenuButton;

        [Header("Game over")]
        public Text gameOverReasonText;
        public Button gameOverRestartButton;

        [Header("Completion")]
        public Text completeStatsText;
        public Button completeRestartButton;
        public Button completeMenuButton;

        private GameManager gameManager;
        private Coroutine toastRoutine;

        public bool Initialized { get; private set; }
        public string LastToast { get; private set; } = string.Empty;

        public void Initialize(GameManager manager)
        {
            gameManager = manager;
            Wire(startButton, manager.StartGame);
            Wire(pauseButton, manager.PauseGame);
            Wire(restartButton, manager.RestartGame);
            Wire(resumeButton, manager.ResumeGame);
            Wire(pauseRestartButton, manager.RestartGame);
            Wire(pauseMenuButton, manager.ReturnToMainMenu);
            Wire(gameOverRestartButton, manager.RestartGame);
            Wire(completeRestartButton, manager.RestartGame);
            Wire(completeMenuButton, manager.ReturnToMainMenu);
            Initialized = true;
        }

        private static void Wire(Button button, UnityEngine.Events.UnityAction action)
        {
            if (button == null)
            {
                return;
            }

            button.onClick.RemoveAllListeners();
            button.onClick.AddListener(action);
        }

        public void SetScore(int collected, int total)
        {
            if (bananaText != null)
            {
                bananaText.text = $"BANANAS  {collected} / {total}";
            }
        }

        public void SetObjective(string label)
        {
            if (objectiveText != null)
            {
                objectiveText.text = "OBJECTIVE  " + label;
            }
        }

        public void SetBest(int best)
        {
            if (bestText != null)
            {
                bestText.text = $"BEST  {best}";
            }

            if (mainMenuBestText != null)
            {
                mainMenuBestText.text = best > 0 ? $"Best score: {best}" : "No completed runs yet";
            }
        }

        public void ShowState(GameState state)
        {
            SetActive(hudGroup, state == GameState.Playing || state == GameState.Paused);
            SetActive(mainMenuPanel, state == GameState.MainMenu);
            SetActive(pausePanel, state == GameState.Paused);
            SetActive(gameOverPanel, state == GameState.GameOver);
            SetActive(completePanel, state == GameState.LevelCompleted);

            if (pauseButton != null)
            {
                pauseButton.interactable = state == GameState.Playing;
            }

            if (restartButton != null)
            {
                restartButton.interactable = state == GameState.Playing || state == GameState.Paused;
            }
        }

        public void SetGameOverReason(string reason)
        {
            if (gameOverReasonText != null)
            {
                gameOverReasonText.text = string.IsNullOrEmpty(reason) ? "The run ends here." : reason;
            }
        }

        public void SetCompletionStats(int score, int total, int best, bool newBest)
        {
            if (completeStatsText == null)
            {
                return;
            }

            completeStatsText.text =
                $"Bananas: {score} / {total}\n" +
                (newBest ? $"NEW BEST SCORE: {best}" : $"Best score: {best}");
        }

        public void ShowToast(string message, float seconds = 2.2f)
        {
            LastToast = message;
            if (toastText == null)
            {
                return;
            }

            if (toastRoutine != null)
            {
                StopCoroutine(toastRoutine);
            }

            toastRoutine = StartCoroutine(ToastRoutine(message, seconds));
        }

        public void ClearToast()
        {
            LastToast = string.Empty;
            if (toastRoutine != null)
            {
                StopCoroutine(toastRoutine);
                toastRoutine = null;
            }

            if (toastText != null)
            {
                toastText.text = string.Empty;
                toastText.gameObject.SetActive(false);
            }
        }

        private IEnumerator ToastRoutine(string message, float seconds)
        {
            toastText.text = message;
            toastText.gameObject.SetActive(true);
            yield return new WaitForSecondsRealtime(seconds);
            toastText.text = string.Empty;
            toastText.gameObject.SetActive(false);
            toastRoutine = null;
        }

        private static void SetActive(GameObject target, bool active)
        {
            if (target != null && target.activeSelf != active)
            {
                target.SetActive(active);
            }
        }
    }
}
