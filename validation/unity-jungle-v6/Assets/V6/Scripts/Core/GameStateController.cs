using System;
using System.Collections.Generic;
using UnityEngine;

namespace V6
{
    /// <summary>
    /// Pure gameplay state machine. Holds the current state, enforces the
    /// transition table and raises a single change event. It never touches
    /// Unity time, input or UI so it can be unit tested in EditMode.
    /// </summary>
    public class GameStateController : MonoBehaviour
    {
        private static readonly Dictionary<GameState, GameState[]> Allowed =
            new Dictionary<GameState, GameState[]>
            {
                { GameState.Initializing, new[] { GameState.MainMenu, GameState.Playing } },
                { GameState.MainMenu, new[] { GameState.Playing } },
                { GameState.Playing, new[]
                    {
                        GameState.Paused, GameState.GameOver, GameState.LevelCompleted,
                        GameState.Restarting, GameState.MainMenu,
                    }
                },
                { GameState.Paused, new[] { GameState.Playing, GameState.Restarting, GameState.MainMenu } },
                { GameState.GameOver, new[] { GameState.Restarting, GameState.MainMenu } },
                { GameState.LevelCompleted, new[] { GameState.Restarting, GameState.MainMenu } },
                { GameState.Restarting, new[] { GameState.Playing, GameState.MainMenu } },
            };

        [SerializeField] private GameState initialState = GameState.Initializing;

        public GameState Current { get; private set; } = GameState.Initializing;

        /// <summary>Raised as (previous, next) after a legal transition.</summary>
        public event Action<GameState, GameState> StateChanged;

        /// <summary>Raised when a transition is requested but rejected.</summary>
        public event Action<GameState, GameState> TransitionRejected;

        public bool IsPlaying => Current == GameState.Playing;
        public bool IsPaused => Current == GameState.Paused;
        public bool IsMenu => Current == GameState.MainMenu;
        public bool IsTerminal => Current == GameState.GameOver || Current == GameState.LevelCompleted;

        /// <summary>Gameplay simulation, scoring and collectibles are active.</summary>
        public bool IsGameplayActive => Current == GameState.Playing;

        private void Awake()
        {
            Current = initialState;
        }

        public bool CanTransition(GameState next)
        {
            if (next == Current)
            {
                return false;
            }

            return Allowed.TryGetValue(Current, out var targets) &&
                   Array.IndexOf(targets, next) >= 0;
        }

        public bool TryTransition(GameState next)
        {
            if (!CanTransition(next))
            {
                Debug.LogWarning($"[V6] Illegal state transition {Current} -> {next}");
                TransitionRejected?.Invoke(Current, next);
                return false;
            }

            GameState previous = Current;
            Current = next;
            StateChanged?.Invoke(previous, next);
            return true;
        }

        /// <summary>Used by tests to restore a known state without bypassing the table.</summary>
        public void ResetTo(GameState state)
        {
            GameState previous = Current;
            Current = state;
            if (previous != state)
            {
                StateChanged?.Invoke(previous, state);
            }
        }
    }
}
