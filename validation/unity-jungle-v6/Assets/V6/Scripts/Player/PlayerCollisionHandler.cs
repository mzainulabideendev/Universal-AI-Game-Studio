using UnityEngine;

namespace V6
{
    /// <summary>
    /// Forwards real collision events to the game manager: hazard triggers
    /// (river water) end the run, and controller hits are counted for audit.
    /// </summary>
    [RequireComponent(typeof(CharacterController))]
    public class PlayerCollisionHandler : MonoBehaviour
    {
        [SerializeField] private GameManager gameManager;

        public int EnvironmentCollisions { get; private set; }
        public int HazardTriggers { get; private set; }
        public string LastColliderName { get; private set; } = string.Empty;

        public void Initialize(GameManager manager) => gameManager = manager;

        private void OnControllerColliderHit(ControllerColliderHit hit)
        {
            EnvironmentCollisions++;
            LastColliderName = hit.collider != null ? hit.collider.name : string.Empty;
            if (hit.collider != null && IsHazard(hit.collider, hit.collider.name))
            {
                HazardTriggers++;
                gameManager?.OnPlayerEnteredHazard(hit.collider.name);
            }
        }

        private void OnTriggerEnter(Collider other)
        {
            if (other == null)
            {
                return;
            }

            if (!IsHazard(other, other.name))
            {
                return;
            }

            HazardTriggers++;
            LastColliderName = other.name;
            gameManager?.OnPlayerEnteredHazard(other.name);
        }

        private static bool IsHazard(Collider collider, string rawName)
        {
            if (collider != null && collider.CompareTag("Hazard"))
            {
                return true;
            }

            string name = (rawName ?? string.Empty).ToLowerInvariant();
            return name.Contains("river_water") || name == "river" ||
                   name.Contains("hazard");
        }
    }
}
