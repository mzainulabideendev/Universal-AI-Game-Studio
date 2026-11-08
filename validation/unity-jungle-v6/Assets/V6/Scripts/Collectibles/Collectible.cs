using System.Collections;
using UnityEngine;

namespace V6
{
    /// <summary>
    /// A world-space banana. Collection is idempotent: trigger and proximity
    /// paths both funnel through <see cref="TryCollect"/> and the manager's
    /// uniqueness check. Values and placement are configurable.
    /// </summary>
    public class Collectible : MonoBehaviour
    {
        [SerializeField] private int value = 1;
        [SerializeField] private float spinSpeed = 95f;
        [SerializeField] private float bobHeight = 0.16f;
        [SerializeField] private float bobSpeed = 2.4f;
        [SerializeField] private float pickupRadius = 1.15f;
        [SerializeField] private float collectEffectSeconds = 0.18f;

        private CollectibleManager manager;
        private Vector3 basePosition;
        private Vector3 baseScale = Vector3.one;
        private bool collected;

        public int Value => value;
        public bool Collected => collected;
        public Vector3 BasePosition => basePosition;

        public void Initialize(CollectibleManager owningManager, Vector3 spawnPosition)
        {
            manager = owningManager;
            basePosition = spawnPosition;
            baseScale = transform.localScale;
            transform.position = spawnPosition;
            collected = false;
            gameObject.SetActive(true);
        }

        public void SetValue(int newValue) => value = Mathf.Max(0, newValue);

        private void Update()
        {
            if (collected || manager == null || !manager.GameplayActive)
            {
                return;
            }

            transform.Rotate(0f, spinSpeed * Time.deltaTime, 0f, Space.World);
            float bob = Mathf.Sin(Time.time * bobSpeed) * bobHeight;
            transform.position = basePosition + Vector3.up * bob;

            if (manager.Player != null)
            {
                Vector3 delta = manager.Player.position + Vector3.up * 0.8f - transform.position;
                if (delta.sqrMagnitude <= pickupRadius * pickupRadius)
                {
                    TryCollect();
                }
            }
        }

        private void OnTriggerEnter(Collider other)
        {
            if (other.CompareTag("Player"))
            {
                TryCollect();
            }
        }

        /// <summary>Returns false when already collected or gameplay is inactive.</summary>
        public bool TryCollect()
        {
            if (collected || manager == null || !manager.GameplayActive)
            {
                return false;
            }

            collected = true;
            manager.NotifyCollected(this);
            StartCoroutine(CollectEffect());
            return true;
        }

        private IEnumerator CollectEffect()
        {
            float elapsed = 0f;
            Vector3 start = transform.localScale;
            while (elapsed < collectEffectSeconds)
            {
                elapsed += Time.deltaTime;
                float t = Mathf.Clamp01(elapsed / collectEffectSeconds);
                transform.localScale = Vector3.Lerp(start, Vector3.zero, t);
                transform.position = basePosition + Vector3.up * (0.35f * t);
                yield return null;
            }

            gameObject.SetActive(false);
            transform.localScale = baseScale;
        }

        public void ResetCollectible()
        {
            StopAllCoroutines();
            collected = false;
            transform.localScale = baseScale;
            transform.position = basePosition;
            gameObject.SetActive(true);
        }
    }
}
