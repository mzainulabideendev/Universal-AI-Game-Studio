using UnityEngine;

namespace V6
{
    public struct GroundInfo
    {
        public bool IsGrounded;
        public Vector3 Normal;
        public float Distance;
        public float SlopeAngle;
        public Collider Collider;
        public bool IsWalkableSlope;
    }

    /// <summary>
    /// Ground probing for a CharacterController. CharacterController.isGrounded
    /// is combined with a short sphere cast and a ray cast for the surface
    /// normal, so slopes, steps and ledges are reported consistently.
    /// </summary>
    public class GroundDetector
    {
        public LayerMask Mask = ~0;
        public float ProbeDistance = 0.18f;
        public float RadiusFactor = 0.92f;

        public GroundInfo Detect(CharacterController controller, float slopeLimit)
        {
            var result = new GroundInfo
            {
                Normal = Vector3.up,
                IsWalkableSlope = true,
                Distance = float.PositiveInfinity,
            };

            if (controller == null)
            {
                return result;
            }

            Vector3 center = controller.transform.TransformPoint(controller.center);
            float halfHeight = Mathf.Max(controller.height * 0.5f, controller.radius);
            Vector3 feetSphere = center - Vector3.up * (halfHeight - controller.radius);
            float radius = controller.radius * Mathf.Clamp(RadiusFactor, 0.5f, 1f);

            bool sphereHit = Physics.SphereCast(
                feetSphere + Vector3.up * 0.03f,
                radius,
                Vector3.down,
                out RaycastHit sphereHitInfo,
                ProbeDistance + 0.05f,
                Mask,
                QueryTriggerInteraction.Ignore);

            bool rayHit = Physics.Raycast(
                center,
                Vector3.down,
                out RaycastHit rayHitInfo,
                halfHeight + ProbeDistance + 0.1f,
                Mask,
                QueryTriggerInteraction.Ignore);

            bool grounded = controller.isGrounded || sphereHit;
            result.IsGrounded = grounded;

            if (rayHit)
            {
                result.Normal = rayHitInfo.normal;
                result.Collider = rayHitInfo.collider;
                result.Distance = rayHitInfo.distance - halfHeight;
            }
            else if (sphereHit)
            {
                result.Normal = sphereHitInfo.normal;
                result.Collider = sphereHitInfo.collider;
                result.Distance = sphereHitInfo.distance;
            }

            result.SlopeAngle = Vector3.Angle(result.Normal, Vector3.up);
            result.IsWalkableSlope = result.SlopeAngle <= slopeLimit + 0.5f;
            return result;
        }
    }
}
