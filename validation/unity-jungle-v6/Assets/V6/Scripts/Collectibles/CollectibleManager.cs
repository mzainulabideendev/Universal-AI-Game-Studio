using System;
using System.Collections.Generic;
using UnityEngine;

namespace V6
{
    public struct CollectibleValidation
    {
        public int Total;
        public int WithTrigger;
        public int ExactlyOnRoute;
        public int Grounded;
        public int Duplicates;
        public List<string> Problems;
        public bool Passed;
    }

    /// <summary>
    /// Owns the collectible set, ground placement validation, uniqueness and
    /// reset. Score cannot advance without a real <see cref="NotifyCollected"/>.
    /// </summary>
    public class CollectibleManager : MonoBehaviour
    {
        [SerializeField] private Collectible[] collectibles;
        [SerializeField] private Transform player;
        [SerializeField] private GameStateController states;
        [SerializeField] private AudioManager audioManager;
        [SerializeField] private LevelManager level;

        private readonly HashSet<int> collectedIds = new HashSet<int>();

        public Collectible[] Collectibles => collectibles;
        public Transform Player => player;
        public int Total => collectibles != null ? collectibles.Length : 0;
        public int CollectedCount => collectedIds.Count;
        public bool GameplayActive => states == null || states.IsGameplayActive;

        public event Action<Collectible> Collected;

        public void Configure(Collectible[] items)
        {
            collectibles = items;
        }

        public void Initialize(LevelManager levelManager, Transform playerTransform,
            GameStateController stateController, AudioManager audio)
        {
            level = levelManager;
            player = playerTransform;
            states = stateController;
            audioManager = audio;
            if (collectibles == null)
            {
                collectibles = Array.Empty<Collectible>();
            }

            foreach (Collectible collectible in collectibles)
            {
                if (collectible == null)
                {
                    continue;
                }

                Vector3 spawn = collectible.transform.position;
                if (level != null)
                {
                    spawn = level.SnapToGround(spawn, 1.0f, 12f);
                }

                collectible.Initialize(this, spawn);
            }

            ResetAll();
        }

        public void NotifyCollected(Collectible collectible)
        {
            if (collectible == null)
            {
                return;
            }

            int id = collectible.GetInstanceID();
            if (!collectedIds.Add(id))
            {
                return;
            }

            Collected?.Invoke(collectible);
            GameplayEventBus.RaiseBananaCollected(CollectedCount, Total);
        }

        public void ResetAll()
        {
            collectedIds.Clear();
            if (collectibles == null)
            {
                return;
            }

            foreach (Collectible collectible in collectibles)
            {
                if (collectible != null)
                {
                    collectible.ResetCollectible();
                }
            }
        }

        public CollectibleValidation ValidatePlacement()
        {
            var report = new CollectibleValidation
            {
                Total = Total,
                Problems = new List<string>(),
            };

            var positions = new HashSet<string>();
            foreach (Collectible collectible in collectibles)
            {
                if (collectible == null)
                {
                    report.Problems.Add("null collectible entry");
                    continue;
                }

                var trigger = collectible.GetComponent<Collider>();
                if (trigger != null && trigger.isTrigger)
                {
                    report.WithTrigger++;
                }
                else
                {
                    report.Problems.Add($"{collectible.name}: missing trigger collider");
                }

                if (collectible.BasePosition.sqrMagnitude > 0.01f)
                {
                    report.ExactlyOnRoute++;
                }

                if (level == null || level.HasGroundBelow(collectible.transform.position, 12f))
                {
                    report.Grounded++;
                }
                else
                {
                    report.Problems.Add($"{collectible.name}: no ground below");
                }

                string key = $"{collectible.BasePosition.x:F1},{collectible.BasePosition.z:F1}";
                if (!positions.Add(key))
                {
                    report.Duplicates++;
                    report.Problems.Add($"{collectible.name}: duplicate XZ position {key}");
                }
            }

            report.Passed = report.Total > 0 &&
                            report.WithTrigger == report.Total &&
                            report.Grounded == report.Total &&
                            report.Duplicates == 0;
            return report;
        }
    }
}
