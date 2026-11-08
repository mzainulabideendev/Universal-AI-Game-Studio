using System;

namespace V6
{
    /// <summary>
    /// Lightweight telemetry/event fan-out. Gameplay systems keep direct
    /// references for control flow; this bus is for observers (analytics,
    /// tests, future UI) and is reset every time a scene bootstraps.
    /// </summary>
    public static class GameplayEventBus
    {
        public static event Action<GameState, GameState> StateChanged;
        public static event Action<int, int> BananaCollected;   // collected, total
        public static event Action<int, int> ObjectiveProgress; // current, target
        public static event Action LevelCompleted;
        public static event Action PlayerLanded;
        public static event Action PlayerFell;
        public static event Action PlayerJumped;

        public static void RaiseStateChanged(GameState previous, GameState next) =>
            StateChanged?.Invoke(previous, next);

        public static void RaiseBananaCollected(int collected, int total) =>
            BananaCollected?.Invoke(collected, total);

        public static void RaiseObjectiveProgress(int current, int target) =>
            ObjectiveProgress?.Invoke(current, target);

        public static void RaiseLevelCompleted() => LevelCompleted?.Invoke();
        public static void RaisePlayerLanded() => PlayerLanded?.Invoke();
        public static void RaisePlayerFell() => PlayerFell?.Invoke();
        public static void RaisePlayerJumped() => PlayerJumped?.Invoke();

        /// <summary>Clears all subscribers. Called by bootstrap and by test setup.</summary>
        public static void Reset()
        {
            StateChanged = null;
            BananaCollected = null;
            ObjectiveProgress = null;
            LevelCompleted = null;
            PlayerLanded = null;
            PlayerFell = null;
            PlayerJumped = null;
        }
    }
}
