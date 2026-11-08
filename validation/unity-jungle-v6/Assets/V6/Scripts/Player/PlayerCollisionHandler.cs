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
        }

        private void OnTriggerEnter(Collider other)
        {
            if (other == null)
            {
                return;
            }

            string name = other.name.ToLowerInvariant();
            bool hazard = other.CompareTag("Hazard") || name.Contains("river_water") ||
                          name == "river" || name.Contains("hazard");
            if (!hazard)
            {
                return;
            }

            HazardTriggers++;
            LastColliderName = other.name;
            gameManager?.OnPlayerEnteredHazard(other.name);
        }
    }
}
