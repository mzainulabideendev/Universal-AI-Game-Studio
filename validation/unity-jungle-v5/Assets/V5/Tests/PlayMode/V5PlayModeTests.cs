using System.Collections;
using System.Linq;
using NUnit.Framework;
using UnityEngine;
using UnityEngine.SceneManagement;
using UnityEngine.TestTools;
using V5;

namespace V5.Tests
{
    public class V5PlayModeTests
    {
        private MonkeyController player;
        private GameManager manager;

        [UnitySetUp]
        public IEnumerator SetUp()
        {
            var load = SceneManager.LoadSceneAsync("JungleMonkey");
            while (!load.isDone)
            {
                yield return null;
            }
            yield return null;
            player = Object.FindFirstObjectByType<MonkeyController>();
            manager = Object.FindFirstObjectByType<GameManager>();
            Assert.IsNotNull(player, "MonkeyController missing from scene");
            Assert.IsNotNull(manager, "GameManager missing from scene");
        }

        [Test]
        public void SceneContainsPlayerEnvironmentAndHud()
        {
            Assert.IsNotNull(player.GetComponent<CharacterController>());
            Assert.IsNotNull(player.Animator, "Animator missing on the monkey");
            Assert.IsNotNull(manager.Hud, "HUD missing");
            Assert.GreaterOrEqual(manager.TotalBananas, 10);
            Assert.IsNotNull(GameObject.Find("JungleEnvironment"), "Jungle environment missing");
            Assert.IsNotNull(GameObject.Find("Main Camera"), "Camera missing");
        }

        [Test]
        public void NoMissingScriptsOrMaterials()
        {
            var objects = Object.FindObjectsByType<GameObject>(FindObjectsSortMode.None);
            foreach (var go in objects)
            {
                foreach (var component in go.GetComponents<Component>())
                {
                    Assert.IsNotNull(component, $"Missing script on {go.name}");
                }
                foreach (var renderer in go.GetComponents<Renderer>())
                {
                    Assert.IsNotNull(renderer.sharedMaterial,
                        $"Missing material on {go.name}");
                    Assert.IsFalse(renderer.sharedMaterial.shader == null,
                        $"Missing shader on {go.name}");
                }
            }
        }

        [UnityTest]
        public IEnumerator PlayerIsGroundedByPhysics()
        {
            yield return new WaitForSeconds(0.6f);
            Assert.IsTrue(player.IsGrounded, "Player did not detect ground");
            Assert.Less(Mathf.Abs(player.transform.position.y - player.StartPosition.y), 1.0f,
                "Player fell through the terrain");
        }

        [UnityTest]
        public IEnumerator MovementChangesPlayerPosition()
        {
            Vector3 start = player.transform.position;
            player.SetTestInput(Vector2.up, false, false);
            yield return new WaitForSeconds(0.8f);
            player.ClearTestInput();
            float moved = Vector3.Distance(start, player.transform.position);
            Assert.Greater(moved, 1.0f, "Player did not move");
        }

        [UnityTest]
        public IEnumerator JumpRaisesPlayerAboveGround()
        {
            yield return new WaitForSeconds(0.5f);
            float startY = player.transform.position.y;
            player.SetTestInput(Vector2.zero, true, false);
            yield return new WaitForSeconds(0.35f);
            Assert.Greater(player.transform.position.y, startY + 0.2f,
                "Jump did not raise the player");
            player.ClearTestInput();
        }

        [UnityTest]
        public IEnumerator CollectibleIncrementsScoreAndDisappears()
        {
            var banana = manager.Bananas[0];
            player.Teleport(banana.transform.position - Vector3.up * 0.85f);
            yield return new WaitForSeconds(0.25f);
            Assert.GreaterOrEqual(manager.Score, 1, "Score did not increase");
            Assert.IsFalse(banana.gameObject.activeSelf, "Collected banana stayed active");
        }

        [UnityTest]
        public IEnumerator RestartResetsScorePlayerAndBananas()
        {
            var banana = manager.Bananas[0];
            player.Teleport(banana.transform.position - Vector3.up * 0.85f);
            yield return new WaitForSeconds(0.25f);
            Assert.GreaterOrEqual(manager.Score, 1);

            manager.ResetState();
            yield return null;
            Assert.AreEqual(0, manager.Score, "Score was not reset");
            Assert.IsTrue(banana.gameObject.activeSelf, "Banana was not restored");
            Assert.Less(Vector3.Distance(player.transform.position, manager.PlayerStart), 0.25f,
                "Player was not returned to the start");
        }

        [UnityTest]
        public IEnumerator AnimatorReactsToMovement()
        {
            player.SetTestInput(Vector2.up, false, true);
            yield return new WaitForSeconds(0.5f);
            Assert.IsNotNull(player.Animator);
            Assert.Greater(player.Animator.GetFloat("Speed"), 0.1f,
                "Animator Speed parameter did not update");
            player.ClearTestInput();
        }

        [Test]
        public void HudDisplaysBananaProgress()
        {
            Assert.IsNotNull(manager.Hud.scoreText);
            StringAssert.Contains("Bananas", manager.Hud.scoreText.text);
            StringAssert.Contains("/", manager.Hud.scoreText.text);
        }
    }
}
