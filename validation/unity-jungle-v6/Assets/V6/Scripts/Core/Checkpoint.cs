using UnityEngine;

namespace V6
{
    /// <summary>Trigger volume that records a safe respawn point.</summary>
    [RequireComponent(typeof(SphereCollider))]
    public class Checkpoint : MonoBehaviour
    {
        [SerializeField] private int index;
        [SerializeField] private CheckpointManager manager;
        [SerializeField] private float triggerRadius = 2.6f;

        public int Index => index;
        public Vector3 RespawnPosition => transform.position;

        public void Configure(int checkpointIndex, CheckpointManager owningManager)
        {
            index = checkpointIndex;
            manager = owningManager;
            var sphere = GetComponent<SphereCollider>();
            if (sphere != null)
            {
                sphere.isTrigger = true;
                sphere.radius = triggerRadius;
            }
        }

        private void OnTriggerEnter(Collider other)
        {
            if (other.CompareTag("Player"))
            {
                manager?.Register(this);
            }
        }
    }
}
