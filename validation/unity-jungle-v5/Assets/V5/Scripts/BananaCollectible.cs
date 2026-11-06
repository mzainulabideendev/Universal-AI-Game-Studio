using UnityEngine;

namespace V5
{
    public class BananaCollectible : MonoBehaviour
    {
        public float spinSpeed = 90f;
        public float bobHeight = 0.18f;
        public float bobSpeed = 2.2f;
        public float collectRadius = 0.9f;
        public GameManager manager;

        private Vector3 basePosition;
        private bool collected;

        private void Start()
        {
            basePosition = transform.position;
        }

        private void Update()
        {
            if (collected)
            {
                return;
            }

            transform.Rotate(0f, spinSpeed * Time.deltaTime, 0f, Space.World);
            transform.position = basePosition + Vector3.up * Mathf.Sin(Time.time * bobSpeed) * bobHeight;

            if (manager != null && manager.Player != null &&
                Vector3.Distance(manager.Player.position, transform.position) < collectRadius)
            {
                Collect();
            }
        }

        private void OnTriggerEnter(Collider other)
        {
            if (other.CompareTag("Player"))
            {
                Collect();
            }
        }

        public void Collect()
        {
            if (collected)
            {
                return;
            }
            collected = true;
            if (manager != null)
            {
                manager.AddBanana();
            }
            gameObject.SetActive(false);
        }

        public void ResetBanana()
        {
            collected = false;
            transform.position = basePosition;
            gameObject.SetActive(true);
        }
    }
}
