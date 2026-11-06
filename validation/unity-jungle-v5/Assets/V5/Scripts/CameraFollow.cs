using UnityEngine;

namespace V5
{
    public class CameraFollow : MonoBehaviour
    {
        public Transform target;
        public Vector3 offset = new Vector3(0f, 4.2f, -8.5f);
        public float smoothing = 6f;

        public void SetTarget(Transform value)
        {
            target = value;
            if (target != null)
            {
                transform.position = target.position + offset;
                transform.LookAt(target.position + Vector3.up * 1.2f);
            }
        }

        private void LateUpdate()
        {
            if (target == null)
            {
                return;
            }

            Vector3 desired = target.position + offset;
            float blend = 1f - Mathf.Exp(-smoothing * Time.deltaTime);
            transform.position = Vector3.Lerp(transform.position, desired, blend);
            transform.LookAt(target.position + Vector3.up * 1.2f);
        }
    }
}
