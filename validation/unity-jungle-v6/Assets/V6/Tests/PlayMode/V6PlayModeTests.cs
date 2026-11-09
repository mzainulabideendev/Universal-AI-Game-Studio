using System.Collections;
using System.Linq;
using NUnit.Framework;
using UnityEngine;
using UnityEngine.SceneManagement;
using UnityEngine.TestTools;

namespace V6.Tests
{
    /// <summary>
    /// End-to-end PlayMode tests against the generated Phase 5 scene. Every
    /// assertion uses the real gameplay objects, physics and state machine.
    /// </summary>
    public class V6PlayModeTests
    {
        private const string SceneName = "JungleMonkeyV6";

        private GameManager manager;
        private PlayerMovement player;
        private GameObject syntheticWall;

        [UnitySetUp]
        public IEnumerator SetUp()
        {
            Time.timeScale = 1f;
            var load = SceneManager.LoadSceneAsync(SceneName);
            Assert.IsNotNull(load, "Scene '" + SceneName + "' is not in build settings");
            while (!load.isDone)
            {
                yield return null;
            }

            yield return null;
            manager = Object.FindFirstObjectByType<GameManager>();
            player = Object.FindFirstObjectByType<PlayerMovement>();
            Assert.IsNotNull(manager, "GameManager missing from scene");
            Assert.IsNotNull(player, "PlayerMovement missing from scene");
            manager.StartGame();
            yield return null;
            yield return new WaitForSecondsRealtime(0.4f);
        }

        [TearDown]
        public void TearDown()
        {
            Time.timeScale = 1f;
            player?.ClearTestInput();
            if (syntheticWall != null)
            {
                Object.Destroy(syntheticWall);
            }
        }

        [Test]
        public void SceneContainsRealPlayerEnvironmentCameraAndUi()
        {
            Assert.IsNotNull(player.GetComponent<CharacterController>());
            Assert.IsNotNull(player.GetComponentInChildren<Animator>(), "Animator missing");
            Assert.IsNotNull(GameObject.Find("JungleEnvironment"), "Environment missing");
            Assert.IsNotNull(GameObject.Find("Main Camera"), "Camera missing");
            Assert.IsNotNull(manager.Destination, "Destination missing");
            Assert.IsNotNull(manager.UI, "UI missing");
            Assert.IsNotNull(manager.Level, "LevelManager missing");
            Assert.GreaterOrEqual(manager.TotalBananas, 10);
            Assert.GreaterOrEqual(manager.Checkpoints.CheckpointCount, 1);
        }

        [Test]
        public void NoMissingScriptsMaterialsOrShaders()
        {
            foreach (var go in Object.FindObjectsByType<GameObject>(FindObjectsSortMode.None))
            {
                foreach (var component in go.GetComponents<Component>())
                {
                    Assert.IsNotNull(component, $"Missing script on {go.name}");
                }

                foreach (var renderer in go.GetComponents<Renderer>())
                {
                    Assert.IsNotNull(renderer.sharedMaterial, $"Missing material on {go.name}");
                    Assert.IsNotNull(renderer.sharedMaterial.shader, $"Missing shader on {go.name}");
                }
            }
        }

        [UnityTest]
        public IEnumerator PlayerSpawnsOnGroundAndStaysThere()
        {
            yield return new WaitForSeconds(0.6f);
            Assert.IsTrue(player.IsGrounded, "Player never detected ground");
            Assert.Greater(player.transform.position.y, 0f, "Player fell below the terrain");
            Assert.Less(Vector3.Distance(player.transform.position, manager.Level.SpawnPosition), 1.2f,
                "Player did not settle at the spawn point");
        }

        [UnityTest]
        public IEnumerator PlayerMovesWhenInputIsApplied()
        {
            Vector3 start = player.transform.position;
            player.SetTestInput(Vector2.up, false, false);
            yield return new WaitForSeconds(1.0f);
            player.ClearTestInput();
            Assert.Greater(Vector3.Distance(start, player.transform.position), 0.8f,
                "Player did not move");
        }

        [UnityTest]
        public IEnumerator PlayerJumpsRaisesAndLands()
        {
            yield return new WaitForSeconds(0.4f);
            float startY = player.transform.position.y;
            player.SetTestInput(Vector2.zero, true, false);
            yield return new WaitForSeconds(0.3f);
            Assert.Greater(player.JumpCount, 0, "Jump was not registered");
            Assert.Greater(player.transform.position.y, startY + 0.15f,
                "Jump did not raise the player");

            player.ClearTestInput();
            yield return new WaitForSeconds(1.6f);
            Assert.IsTrue(player.IsGrounded, "Player did not land");
            Assert.Less(Mathf.Abs(player.transform.position.y - startY), 1.0f,
                "Player did not return near the ground");
        }

        [UnityTest]
        public IEnumerator DoubleJumpIsRejected()
        {
            yield return new WaitForSeconds(0.3f);
            player.SetTestInput(Vector2.zero, true, false);
            yield return new WaitForSeconds(0.15f);
            int afterFirst = player.JumpCount;
            Assert.Greater(afterFirst, 0, "First jump was not registered");
            player.SetTestInput(Vector2.zero, true, false);
            yield return new WaitForSeconds(0.2f);
            Assert.AreEqual(afterFirst, player.JumpCount, "Air jump was accepted");
            player.ClearTestInput();
        }

        [UnityTest]
        public IEnumerator BananaCollectionIncrementsScoreAndHidesObject()
        {
            Collectible banana = manager.Collectibles.Collectibles.First(c => c != null && !c.Collected);
            int scoreBefore = manager.ScoreValue;
            player.Teleport(banana.transform.position - Vector3.up * 0.85f);
            yield return new WaitForSeconds(0.35f);

            Assert.Greater(manager.ScoreValue, scoreBefore, "Score did not increase");
            Assert.AreEqual(1, manager.CollectedBananas, "Collected count is wrong");
            Assert.IsTrue(banana.Collected, "Collectible did not record collection");
            Assert.IsFalse(banana.gameObject.activeSelf, "Collected banana stayed visible");
        }

        [UnityTest]
        public IEnumerator ObjectiveProgressAdvancesWithRealCollections()
        {
            int target = Mathf.Min(2, manager.TotalBananas);
            for (int i = 0; i < target; i++)
            {
                Collectible banana = manager.Collectibles.Collectibles
                    .First(c => c != null && !c.Collected);
                player.Teleport(banana.transform.position - Vector3.up * 0.85f);
                yield return new WaitForSeconds(0.25f);
            }

            Assert.AreEqual(target, manager.Objectives.CollectedBananas);
            Assert.IsFalse(manager.Objectives.IsComplete, "Objective completed too early");
        }

        [UnityTest]
        public IEnumerator PauseStopsMovementAndResumeRestoresIt()
        {
            manager.PauseGame();
            Assert.AreEqual(GameState.Paused, manager.State);
            Vector3 parked = player.transform.position;
            player.SetTestInput(Vector2.up, false, true);
            yield return new WaitForSecondsRealtime(0.45f);
            player.ClearTestInput();
            Assert.Less(Vector3.Distance(parked, player.transform.position), 0.08f,
                "Player moved while paused");

            manager.ResumeGame();
            Assert.AreEqual(GameState.Playing, manager.State);
            Vector3 resumed = player.transform.position;
            player.SetTestInput(Vector2.up, false, true);
            yield return new WaitForSeconds(0.6f);
            player.ClearTestInput();
            Assert.Greater(Vector3.Distance(resumed, player.transform.position), 0.5f,
                "Player did not move after resume");
        }

        [UnityTest]
        public IEnumerator RestartResetsScoreBananasAndPosition()
        {
            Collectible banana = manager.Collectibles.Collectibles.First(c => c != null);
            player.Teleport(banana.transform.position - Vector3.up * 0.85f);
            yield return new WaitForSeconds(0.3f);
            Assert.GreaterOrEqual(manager.ScoreValue, 1);

            manager.RestartGame();
            yield return null;
            yield return new WaitForSeconds(0.3f);

            Assert.AreEqual(GameState.Playing, manager.State);
            Assert.AreEqual(0, manager.ScoreValue, "Score was not reset");
            Assert.AreEqual(0, manager.CollectedBananas, "Collectibles were not reset");
            Assert.IsTrue(banana.gameObject.activeSelf, "Banana was not restored");
            Assert.Less(Vector3.Distance(player.transform.position, manager.Level.SpawnPosition), 1.2f,
                "Player was not returned to spawn");
        }

        [UnityTest]
        public IEnumerator LevelCompletesOnlyAfterAllBananasAndDestination()
        {
            foreach (var collectible in manager.Collectibles.Collectibles)
            {
                collectible.TryCollect();
            }

            yield return new WaitForSeconds(0.3f);
            Assert.AreEqual(manager.TotalBananas, manager.Objectives.CollectedBananas);
            Assert.AreEqual(GameState.Playing, manager.State,
                "Level completed before reaching the destination");

            player.Teleport(manager.Level.DestinationPosition + Vector3.up * 0.8f);
            // Completing the level freezes scaled time, so wait in real time.
            yield return new WaitForSecondsRealtime(0.5f);
            Assert.AreEqual(GameState.LevelCompleted, manager.State,
                "Reaching the destination with all bananas did not complete the level");
        }

        [UnityTest]
        public IEnumerator PlayerCollidesWithSolidObstacle()
        {
            Vector3 forward = player.transform.forward;
            forward.y = 0f;
            forward.Normalize();
            Vector3 wallPosition = player.transform.position + forward * 2.6f;
            syntheticWall = GameObject.CreatePrimitive(PrimitiveType.Cube);
            syntheticWall.name = "SyntheticWall";
            syntheticWall.transform.position = wallPosition;
            syntheticWall.transform.localScale = new Vector3(10f, 4f, 0.6f);
            syntheticWall.transform.rotation = Quaternion.LookRotation(forward, Vector3.up);
            yield return null;

            Vector3 start = player.transform.position;
            player.SetAutomationInput(forward, false);
            yield return new WaitForSeconds(1.2f);
            player.ClearAutomationInput();

            float travelled = Vector3.Distance(start, player.transform.position);
            Assert.Less(travelled, 2.3f, "Player passed through the solid obstacle");
            Assert.Greater(player.GetComponent<PlayerCollisionHandler>().EnvironmentCollisions, 0,
                "No controller collision was reported");
        }

        [UnityTest]
        public IEnumerator AnimatorReceivesLocomotionParameters()
        {
            Animator animator = player.GetComponentInChildren<Animator>();
            Assert.IsNotNull(animator);
            player.SetTestInput(Vector2.up, false, true);
            yield return new WaitForSeconds(0.7f);
            Assert.Greater(animator.GetFloat("Speed"), 0.1f,
                "Animator Speed parameter did not react to movement");
            player.ClearTestInput();
        }

        [UnityTest]
        public IEnumerator RiverHazardEndsRunInGameOverState()
        {
            GameObject water = GameObject.Find("River_Water");
            Assert.IsNotNull(water, "River_Water hazard missing from scene");
            Collider hazard = water.GetComponent<Collider>();
            Assert.IsNotNull(hazard, "River_Water has no trigger collider");

            // Find where the water surface is above the actual terrain below
            // it, so a falling controller has to cross the water collider.
            Vector3? surface = null;
            for (float x = -58f; x <= 58f && surface == null; x += 2f)
            {
                for (float z = -58f; z <= 58f; z += 2f)
                {
                    RaycastHit[] hits = Physics.RaycastAll(
                        new Vector3(x, 70f, z), Vector3.down, 140f,
                        ~0, QueryTriggerInteraction.Collide);
                    float? waterY = null;
                    float? terrainY = null;
                    foreach (RaycastHit hit in hits)
                    {
                        if (hit.collider == hazard)
                        {
                            waterY = hit.point.y;
                        }
                        else if (!terrainY.HasValue)
                        {
                            terrainY = hit.point.y;
                        }
                    }

                    if (waterY.HasValue && terrainY.HasValue &&
                        waterY.Value - terrainY.Value >= 0.4f)
                    {
                        surface = new Vector3(x, waterY.Value, z);
                        break;
                    }
                }
            }

            Assert.IsTrue(surface.HasValue,
                "No river surface above the riverbed was found");
            player.Teleport(surface.Value + Vector3.up * 1.5f);
            // GameOver freezes scaled time, so wait in real time.
            yield return new WaitForSecondsRealtime(1.0f);

            Assert.Greater(player.GetComponent<PlayerCollisionHandler>().HazardTriggers, 0,
                "River contact was never reported as a hazard");
            Assert.AreEqual(GameState.GameOver, manager.State,
                "Entering the river did not end the run");
            Assert.IsFalse(string.IsNullOrEmpty(manager.LastGameOverReason),
                "Game over reason was not recorded");
        }

        [UnityTest]
        public IEnumerator FallingOutOfBoundsReturnsToCheckpointSafely()
        {
            Vector3 before = player.transform.position;
            player.Teleport(new Vector3(0f, -40f, 0f));
            yield return new WaitForSeconds(0.4f);
            Assert.AreEqual(GameState.Playing, manager.State,
                "Falling should respawn, not end the run");
            Assert.Greater(player.transform.position.y, 0f, "Player was not respawned above ground");
            Assert.Less(Vector3.Distance(player.transform.position, before), 30f,
                "Respawn was not near the playable start");
        }
    }
}
