using UnityEngine;

namespace V6
{
    /// <summary>
    /// Owns the playable space: spawn, destination, ground snapping, playable
    /// bounds and the kill plane. Uses physics ray casts against real scene
    /// colliders; it does not rely on terrain height data from Blender.
    /// </summary>
    public class LevelManager : MonoBehaviour
    {
        [Header("Anchors (Blender layout converted to Unity Y-up)")]
        [SerializeField] private Transform spawnPoint;
        [SerializeField] private Transform destinationPoint;

        [Header("Safety")]
        [SerializeField] private float killPlaneY = -8f;
        [SerializeField] private float groundProbeHeight = 40f;
        [SerializeField] private LayerMask groundMask = ~0;
        [SerializeField] private float playableHalfExtent = 60.5f;

        private Vector3 spawnPosition;
        private bool initialized;

        public Vector3 SpawnPosition => spawnPosition;
        public Vector3 DestinationPosition => destinationPoint != null
            ? destinationPoint.position
            : new Vector3(0f, 2f, -46f);
        public float KillPlaneY => killPlaneY;
        public LayerMask GroundMask => groundMask;
        public bool Initialized => initialized;

        public void Configure(Transform spawn, Transform destination)
        {
            spawnPoint = spawn;
            destinationPoint = destination;
        }

        public void Initialize()
        {
            // Never sample the player's own CharacterController: at this point
            // the player object already exists, so a ray from high above the
            // spawn anchor would otherwise hit its capsule and resolve the
            // spawn to the capsule top instead of the terrain.
            LayerMask mask = groundMask;
            int playerLayer = LayerMask.NameToLayer("Player");
            if (playerLayer >= 0)
            {
                mask &= ~(1 << playerLayer);
            }

            if (mask.value == 0)
            {
                mask = ~(1 << 8);
            }

            groundMask = mask;
            Vector3 raw = spawnPoint != null ? spawnPoint.position : new Vector3(0f, 4f, 48f);
            spawnPosition = SnapToGround(raw, 0.05f);
            initialized = true;
            Debug.Log($"[V6] Level spawn={spawnPosition:F2} destination={DestinationPosition:F2}");
        }

        /// <summary>
        /// Casts downward from high above <paramref name="position"/> and
        /// returns the first non-trigger ground point plus clearance.
        /// </summary>
        public Vector3 SnapToGround(Vector3 position, float clearance = 0f, float probeHeight = -1f)
        {
            float probe = probeHeight > 0f ? probeHeight : groundProbeHeight;
            Vector3 origin = position + Vector3.up * probe;
            if (Physics.Raycast(origin, Vector3.down, out RaycastHit hit,
                    probe * 2f + 30f, groundMask, QueryTriggerInteraction.Ignore))
            {
                return hit.point + Vector3.up * clearance;
            }

            return position + Vector3.up * clearance;
        }

        public bool HasGroundBelow(Vector3 position, float probeHeight = -1f)
        {
            float probe = probeHeight > 0f ? probeHeight : groundProbeHeight;
            return Physics.Raycast(position + Vector3.up * probe, Vector3.down,
                probe * 2f + 30f, groundMask, QueryTriggerInteraction.Ignore);
        }

        public bool IsOutsidePlayable(Vector3 position)
        {
            return position.y < killPlaneY ||
                   Mathf.Abs(position.x) > playableHalfExtent ||
                   Mathf.Abs(position.z) > playableHalfExtent;
        }

        public Vector3 ClampToPlayable(Vector3 position)
        {
            float limit = playableHalfExtent - 1f;
            position.x = Mathf.Clamp(position.x, -limit, limit);
            position.z = Mathf.Clamp(position.z, -limit, limit);
            return position;
        }
    }
}
