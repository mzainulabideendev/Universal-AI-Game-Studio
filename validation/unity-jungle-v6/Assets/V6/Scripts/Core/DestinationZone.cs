using UnityEngine;

namespace V6
{
    /// <summary>Goal zone at the jungle ruins.</summary>
    public class DestinationZone : MonoBehaviour
    {
        [SerializeField] private GameManager gameManager;
        [SerializeField] private float triggerRadius = 3.2f;
        [SerializeField] private float proximityRadius = 2.6f;

        private Transform player;
        private bool reported;

        public void Initialize(GameManager manager, Transform playerTransform)
        {
            gameManager = manager;
            player = playerTransform;
            var sphere = GetComponent<SphereCollider>();
            if (sphere == null)
            {
                sphere = gameObject.AddComponent<SphereCollider>();
            }

            sphere.isTrigger = true;
            sphere.radius = triggerRadius;
        }

        private void Update()
        {
            if (reported || player == null || gameManager == null)
            {
                return;
            }

            Vector3 delta = player.position - transform.position;
            delta.y *= 0.45f;
            if (delta.magnitude <= proximityRadius)
            {
                reported = true;
                gameManager.OnDestinationReached();
            }
        }

        private void OnTriggerEnter(Collider other)
        {
            if (reported || !other.CompareTag("Player") || gameManager == null)
            {
                return;
            }

            reported = true;
            gameManager.OnDestinationReached();
        }

        public void ResetZone() => reported = false;
    }
}
