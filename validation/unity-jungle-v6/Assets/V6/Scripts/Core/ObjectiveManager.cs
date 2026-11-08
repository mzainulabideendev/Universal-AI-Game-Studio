using System;
using UnityEngine;

namespace V6
{
    /// <summary>
    /// Minimal functional objective: collect a target number of bananas AND
    /// reach the jungle ruins. Progress only advances from gameplay events.
    /// </summary>
    public class ObjectiveManager : MonoBehaviour
    {
        [SerializeField] private int targetBananas = 10;
        [SerializeField] private bool requiresDestination = true;

        public int TargetBananas => targetBananas;
        public int CollectedBananas { get; private set; }
        public bool DestinationReached { get; private set; }
        public bool RequiresDestination => requiresDestination;

        public bool IsComplete =>
            CollectedBananas >= targetBananas && (!requiresDestination || DestinationReached);

        public event Action<int, int> ProgressChanged;
        public event Action Completed;

        public void Configure(int target, bool destinationRequired)
        {
            targetBananas = Mathf.Max(1, target);
            requiresDestination = destinationRequired;
        }

        public void ResetObjectives()
        {
            CollectedBananas = 0;
            DestinationReached = false;
            ProgressChanged?.Invoke(CollectedBananas, targetBananas);
        }

        /// <summary>Registers one collected banana. Returns false if already complete.</summary>
        public bool RegisterBanana()
        {
            if (CollectedBananas >= targetBananas)
            {
                return false;
            }

            CollectedBananas++;
            ProgressChanged?.Invoke(CollectedBananas, targetBananas);
            EvaluateCompletion();
            return true;
        }

        /// <summary>Registers arrival at the destination. Returns true if complete.</summary>
        public bool MarkDestinationReached()
        {
            if (DestinationReached)
            {
                return IsComplete;
            }

            DestinationReached = true;
            EvaluateCompletion();
            return IsComplete;
        }

        public string ProgressLabel()
        {
            string bananas = $"Bananas {CollectedBananas}/{targetBananas}";
            if (!requiresDestination)
            {
                return bananas;
            }

            return bananas + (DestinationReached ? " · Ruins reached" : " · Reach the ruins");
        }

        private void EvaluateCompletion()
        {
            if (IsComplete)
            {
                Completed?.Invoke();
            }
        }
    }
}
