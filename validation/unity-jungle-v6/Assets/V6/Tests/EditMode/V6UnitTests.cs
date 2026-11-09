using System.Collections.Generic;
using System.IO;
using NUnit.Framework;
using UnityEngine;

namespace V6.Tests
{
    /// <summary>
    /// Deterministic EditMode tests for pure gameplay rules: state machine,
    /// jump maths, scoring, objectives, collectible uniqueness, save-data
    /// validation and camera clamping. No scene is required.
    /// </summary>
    public class V6UnitTests
    {
        private readonly List<GameObject> created = new List<GameObject>();

        private T Add<T>() where T : Component
        {
            var go = new GameObject(typeof(T).Name);
            created.Add(go);
            return go.AddComponent<T>();
        }

        [TearDown]
        public void TearDown()
        {
            foreach (var go in created)
            {
                if (go != null)
                {
                    Object.DestroyImmediate(go);
                }
            }

            created.Clear();
        }

        [Test]
        public void LegalStateTransitionsAreAccepted()
        {
            var states = Add<GameStateController>();
            Assert.AreEqual(GameState.Initializing, states.Current);
            Assert.IsTrue(states.TryTransition(GameState.MainMenu));
            Assert.IsTrue(states.TryTransition(GameState.Playing));
            Assert.IsTrue(states.TryTransition(GameState.Paused));
            Assert.IsTrue(states.TryTransition(GameState.Playing));
            Assert.IsTrue(states.TryTransition(GameState.LevelCompleted));
            Assert.IsTrue(states.TryTransition(GameState.Restarting));
            Assert.IsTrue(states.TryTransition(GameState.Playing));
        }

        [Test]
        public void IllegalStateTransitionsAreRejected()
        {
            var states = Add<GameStateController>();
            states.ResetTo(GameState.MainMenu);
            Assert.IsFalse(states.TryTransition(GameState.Paused));
            Assert.IsFalse(states.CanTransition(GameState.GameOver));
            Assert.AreEqual(GameState.MainMenu, states.Current);

            states.ResetTo(GameState.Playing);
            Assert.IsFalse(states.TryTransition(GameState.Initializing));
            Assert.IsFalse(states.TryTransition(GameState.Playing),
                "Same-state transition must be rejected");
        }

        [Test]
        public void TerminalStatesCannotResumePlayingDirectly()
        {
            var states = Add<GameStateController>();
            states.ResetTo(GameState.Playing);
            Assert.IsTrue(states.TryTransition(GameState.GameOver));
            Assert.IsFalse(states.TryTransition(GameState.Playing));
            Assert.IsTrue(states.TryTransition(GameState.Restarting));
            Assert.IsTrue(states.TryTransition(GameState.Playing));
        }

        [Test]
        public void JumpVelocityMatchesKinematicEquation()
        {
            float velocity = PlayerMovement.ComputeJumpVelocity(1.55f, -24f);
            float expected = Mathf.Sqrt(2f * 1.55f * 24f);
            Assert.AreEqual(expected, velocity, 0.001f);
        }

        [Test]
        public void HigherJumpHeightNeedsMoreVelocity()
        {
            float low = PlayerMovement.ComputeJumpVelocity(1f, -24f);
            float high = PlayerMovement.ComputeJumpVelocity(2f, -24f);
            Assert.Greater(high, low);
        }

        [Test]
        public void ScoreAccumulatesAndBestOnlyImproves()
        {
            var score = Add<ScoreManager>();
            score.Initialize(4);
            Assert.AreEqual(0, score.Score);
            Assert.AreEqual(4, score.BestScore);

            Assert.IsTrue(score.Add(5));
            Assert.AreEqual(5, score.Score);
            Assert.IsFalse(score.Add(0), "Zero value must not count");
        }

        [Test]
        public void ScoreSubmissionRecordsNewBest()
        {
            var score = Add<ScoreManager>();
            score.Initialize(2);
            score.Add(5);
            Assert.IsTrue(score.SubmitToBest());
            Assert.AreEqual(5, score.BestScore);
            Assert.IsFalse(score.SubmitToBest(), "Equal score must not replace best");
            score.ResetScore();
            Assert.AreEqual(0, score.Score);
        }

        [Test]
        public void ObjectiveRequiresBananasAndDestination()
        {
            var objectives = Add<ObjectiveManager>();
            objectives.Configure(3, true);
            objectives.ResetObjectives();
            Assert.IsFalse(objectives.IsComplete);

            for (int i = 0; i < 3; i++)
            {
                Assert.IsTrue(objectives.RegisterBanana());
            }

            Assert.AreEqual(3, objectives.CollectedBananas);
            Assert.IsFalse(objectives.IsComplete, "Destination is still required");
            Assert.IsFalse(objectives.RegisterBanana(), "Target must cap progress");

            Assert.IsTrue(objectives.MarkDestinationReached());
            Assert.IsTrue(objectives.IsComplete);
        }

        [Test]
        public void ObjectiveProgressEventFiresOncePerBanana()
        {
            var objectives = Add<ObjectiveManager>();
            objectives.Configure(2, false);
            objectives.ResetObjectives();
            int events = 0;
            int lastCurrent = -1;
            objectives.ProgressChanged += (current, target) =>
            {
                events++;
                lastCurrent = current;
            };

            objectives.RegisterBanana();
            objectives.RegisterBanana();
            Assert.AreEqual(2, events);
            Assert.AreEqual(2, lastCurrent);
            Assert.IsTrue(objectives.IsComplete);
        }

        [Test]
        public void CollectibleUniquenessPreventsDoubleScore()
        {
            var manager = Add<CollectibleManager>();
            var a = new GameObject("A");
            var b = new GameObject("B");
            created.Add(a);
            created.Add(b);
            var ca = a.AddComponent<Collectible>();
            var cb = b.AddComponent<Collectible>();
            manager.Configure(new[] { ca, cb });

            manager.NotifyCollected(ca);
            manager.NotifyCollected(ca);
            Assert.AreEqual(1, manager.CollectedCount, "Duplicate collection must be ignored");

            manager.NotifyCollected(cb);
            Assert.AreEqual(2, manager.CollectedCount);
            manager.ResetAll();
            Assert.AreEqual(0, manager.CollectedCount);
        }

        [Test]
        public void CollectibleValueIsConfigurable()
        {
            var collectible = Add<Collectible>();
            Assert.AreEqual(1, collectible.Value);
            collectible.SetValue(3);
            Assert.AreEqual(3, collectible.Value);
            collectible.SetValue(-8);
            Assert.AreEqual(0, collectible.Value, "Negative value must clamp to zero");
        }

        [Test]
        public void SaveDataDefaultsAreSafe()
        {
            var data = SaveDataService.Defaults();
            Assert.AreEqual(SaveDataService.CurrentVersion, data.version);
            Assert.AreEqual(0, data.bestScore);
            Assert.IsFalse(data.jungleLevelCompleted);
            Assert.AreEqual(1f, data.masterVolume, 0.0001f);
            StringAssert.DoesNotContain("password", JsonUtility.ToJson(data).ToLowerInvariant());
        }

        [Test]
        public void SaveDataRoundTripsAndValidates()
        {
            var service = Add<SaveDataService>();
            string path = Path.Combine(Path.GetTempPath(), "v6-save-test-" + System.Guid.NewGuid() + ".json");
            service.OverridePath = path;
            try
            {
                var data = SaveDataService.Defaults();
                data.bestScore = 12;
                data.jungleLevelCompleted = true;
                data.totalRuns = 3;
                data.masterVolume = 0.5f;

                Assert.IsTrue(service.Save(data));
                Assert.AreEqual("saved", service.LastStatus);

                var loaded = service.Load();
                Assert.AreEqual("loaded", service.LastStatus);
                Assert.AreEqual(12, loaded.bestScore);
                Assert.IsTrue(loaded.jungleLevelCompleted);
                Assert.AreEqual(3, loaded.totalRuns);
                Assert.AreEqual(0.5f, loaded.masterVolume, 0.0001f);

                var report = service.Validate(loaded);
                Assert.IsTrue(report.valid);
            }
            finally
            {
                if (File.Exists(path)) File.Delete(path);
                if (File.Exists(path + ".tmp")) File.Delete(path + ".tmp");
            }
        }

        [Test]
        public void CorruptSaveFileFallsBackToDefaults()
        {
            var service = Add<SaveDataService>();
            string path = Path.Combine(Path.GetTempPath(), "v6-save-corrupt-" + System.Guid.NewGuid() + ".json");
            service.OverridePath = path;
            File.WriteAllText(path, "{ this is not valid json");
            try
            {
                var loaded = service.Load();
                Assert.AreEqual("corrupt", service.LastStatus);
                Assert.AreEqual(0, loaded.bestScore);
                Assert.IsFalse(File.Exists(path), "Corrupt file should be quarantined");
            }
            finally
            {
                foreach (string file in Directory.GetFiles(Path.GetTempPath(),
                             Path.GetFileName(path) + ".corrupt-*"))
                {
                    File.Delete(file);
                }
            }
        }

        [Test]
        public void SaveValidationRepairsOutOfRangeValues()
        {
            var service = Add<SaveDataService>();
            var data = new SaveData
            {
                version = 99,
                bestScore = -5,
                masterVolume = 4f,
                mouseSensitivity = 0.01f,
            };

            var report = service.Validate(data);
            Assert.IsFalse(report.valid);
            Assert.IsTrue(report.repaired);
            Assert.AreEqual(SaveDataService.CurrentVersion, data.version);
            Assert.AreEqual(0, data.bestScore);
            Assert.AreEqual(1f, data.masterVolume, 0.0001f);
            Assert.AreEqual(0.2f, data.mouseSensitivity, 0.0001f);
        }

        [Test]
        public void CameraPitchClampRespectsBounds()
        {
            Assert.AreEqual(-25f, CameraFollowController.ClampPitch(-90f, -25f, 64f));
            Assert.AreEqual(64f, CameraFollowController.ClampPitch(120f, -25f, 64f));
            Assert.AreEqual(10f, CameraFollowController.ClampPitch(10f, -25f, 64f));
        }
    }
}
