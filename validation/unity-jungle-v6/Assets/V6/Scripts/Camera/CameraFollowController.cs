using UnityEngine;

namespace V6
{
    /// <summary>
    /// Third-person orbit follow camera with smoothed position/rotation and a
    /// sphere-cast collision probe so terrain and large props do not clip
    /// through the view.
    /// </summary>
    public class CameraFollowController : MonoBehaviour
    {
        [Header("Framing")]
        [SerializeField] private float pivotHeight = 1.35f;
        [SerializeField] private float followDistance = 7.2f;
        [SerializeField] private float minDistance = 2.2f;
        [SerializeField] private float positionSmoothing = 9f;
        [SerializeField] private float rotationSmoothing = 12f;
        [SerializeField] private float collisionRadius = 0.28f;

        [Header("Orbit")]
        [SerializeField] private float pitch = 14f;
        [SerializeField] private float minPitch = -25f;
        [SerializeField] private float maxPitch = 64f;
        [SerializeField] private float mouseSensitivity = 2.2f;

        [Header("References")]
        [SerializeField] private Transform target;
        [SerializeField] private PlayerInputHandler inputHandler;

        private float yaw;
        private float currentDistance;
        private bool colliding;
        private Camera cameraComponent;

        public Transform Target => target;
        public float CurrentDistance => currentDistance;
        public bool IsColliding => colliding;
        public float Yaw => yaw;
        public float Pitch => pitch;

        private void Awake()
        {
            cameraComponent = GetComponent<Camera>();
            currentDistance = followDistance;
        }

        public void Initialize(Transform followTarget, PlayerInputHandler input)
        {
            target = followTarget;
            inputHandler = input;
            if (target != null)
            {
                yaw = target.eulerAngles.y;
            }

            Snap();
        }

        public void SetTarget(Transform followTarget) => target = followTarget;

        public void SetSensitivity(float value) => mouseSensitivity = Mathf.Clamp(value, 0.2f, 5f);

        public void AddOrbitInput(Vector2 delta)
        {
            yaw += delta.x * mouseSensitivity;
            pitch = Mathf.Clamp(pitch - delta.y * mouseSensitivity, minPitch, maxPitch);
        }

        public void Snap()
        {
            if (target == null)
            {
                return;
            }

            Vector3 pivot = Pivot();
            Quaternion rotation = Quaternion.Euler(pitch, yaw, 0f);
            Vector3 desired = pivot + rotation * Vector3.back * followDistance;
            if (Physics.SphereCast(pivot, collisionRadius, (desired - pivot).normalized,
                    out RaycastHit hit, followDistance, ~(1 << target.gameObject.layer),
                    QueryTriggerInteraction.Ignore))
            {
                desired = pivot + (desired - pivot).normalized *
                          Mathf.Max(minDistance, hit.distance - collisionRadius);
                currentDistance = Vector3.Distance(pivot, desired);
                colliding = true;
            }
            else
            {
                currentDistance = followDistance;
                colliding = false;
            }

            transform.position = desired;
            transform.rotation = Quaternion.LookRotation(pivot - transform.position, Vector3.up);
        }

        private void LateUpdate()
        {
            if (target == null)
            {
                return;
            }

            if (inputHandler != null)
            {
                AddOrbitInput(inputHandler.MouseDelta);
                if (inputHandler.MouseDelta.sqrMagnitude > 0.0001f && Cursor.lockState != CursorLockMode.Locked
                    && !Application.isEditor)
                {
                    // Keep the cursor hidden in the standalone player while
                    // the player is in control.
                    Cursor.lockState = CursorLockMode.Locked;
                }
            }

            Vector3 pivot = Pivot();
            Quaternion rotation = Quaternion.Euler(pitch, yaw, 0f);
            Vector3 direction = rotation * Vector3.back;
            Vector3 desired = pivot + direction * followDistance;

            colliding = false;
            if (Physics.SphereCast(pivot, collisionRadius, direction, out RaycastHit hit,
                    followDistance, ~(1 << target.gameObject.layer), QueryTriggerInteraction.Ignore))
            {
                float allowed = Mathf.Max(minDistance, hit.distance - collisionRadius);
                desired = pivot + direction * allowed;
                currentDistance = allowed;
                colliding = true;
            }
            else
            {
                currentDistance = followDistance;
            }

            float positionBlend = 1f - Mathf.Exp(-positionSmoothing * Time.deltaTime);
            float rotationBlend = 1f - Mathf.Exp(-rotationSmoothing * Time.deltaTime);
            transform.position = Vector3.Lerp(transform.position, desired, positionBlend);
            Quaternion look = Quaternion.LookRotation(pivot - transform.position, Vector3.up);
            transform.rotation = Quaternion.Slerp(transform.rotation, look, rotationBlend);

            if (cameraComponent != null && colliding && currentDistance < 1.1f)
            {
                // Extremely tight spaces: nudge the pivot forward slightly so
                // the player silhouette stays visible instead of the camera
                // sitting inside the character.
                transform.position += transform.forward * 0.05f;
            }
        }

        private Vector3 Pivot() => target.position + Vector3.up * pivotHeight;

        public static float ClampPitch(float value, float min, float max) =>
            Mathf.Clamp(value, min, max);
    }
}
