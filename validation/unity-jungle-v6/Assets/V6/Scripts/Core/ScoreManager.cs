using System;
using UnityEngine;

namespace V6
{
    /// <summary>
    /// Owns the run score. Score only changes through <see cref="Add"/> which
    /// <see cref="GameManager"/> calls from real collection events.
    /// </summary>
    public class ScoreManager : MonoBehaviour
    {
        [SerializeField] private int bananaValue = 1;

        public int Score { get; private set; }
        public int BestScore { get; private set; }
        public int BananaValue => bananaValue;

        public event Action<int> ScoreChanged;

        public void Initialize(int bestScore)
        {
            BestScore = Mathf.Max(0, bestScore);
            Score = 0;
        }

        public bool Add(int amount)
        {
            int safe = Mathf.Max(0, amount);
            if (safe == 0)
            {
                return false;
            }

            Score += safe;
            ScoreChanged?.Invoke(Score);
            return true;
        }

        public void AddBanana() => Add(bananaValue);

        public void ResetScore()
        {
            Score = 0;
            ScoreChanged?.Invoke(Score);
        }

        /// <summary>Records a new best score and returns true when it changed.</summary>
        public bool SubmitToBest()
        {
            if (Score <= BestScore)
            {
                return false;
            }

            BestScore = Score;
            return true;
        }
    }
}
