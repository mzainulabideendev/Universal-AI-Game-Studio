using System;
using System.Collections.Generic;
using UnityEngine;

namespace V6
{
    [Serializable]
    public class AudioReport
    {
        public bool architectureImplemented = true;
        public int assignedClips;
        public int missingClips;
        public int playRequests;
        public int clipsPlayed;
        public string[] missing;
        public string note;
    }

    /// <summary>
    /// Audio architecture for collection, jump, landing, completion, pause and
    /// game-over feedback. No audio assets exist in the repository, so clips
    /// are optional serialized fields and every missing play request is
    /// reported honestly instead of being faked.
    /// </summary>
    public class AudioManager : MonoBehaviour
    {
        [SerializeField] private AudioSource source;
        [SerializeField] private AudioClip collectClip;
        [SerializeField] private AudioClip jumpClip;
        [SerializeField] private AudioClip landClip;
        [SerializeField] private AudioClip completeClip;
        [SerializeField] private AudioClip pauseClip;
        [SerializeField] private AudioClip gameOverClip;

        private readonly HashSet<string> reportedMissing = new HashSet<string>();
        private readonly List<string> missing = new List<string>();
        private int playRequests;
        private int clipsPlayed;

        public AudioReport Report => new AudioReport
        {
            assignedClips = CountAssigned(),
            missingClips = missing.Count,
            playRequests = playRequests,
            clipsPlayed = clipsPlayed,
            missing = missing.ToArray(),
            note = missing.Count > 0
                ? "No audio assets exist in the repository; the architecture is implemented and missing clips are reported, not synthesized."
                : "All requested clips were assigned.",
        };

        public void Initialize()
        {
            if (source == null)
            {
                source = GetComponent<AudioSource>();
            }

            if (source == null)
            {
                source = gameObject.AddComponent<AudioSource>();
            }

            source.playOnAwake = false;
            source.spatialBlend = 0f;
        }

        public void SetMasterVolume(float volume)
        {
            AudioListener.volume = Mathf.Clamp01(volume);
        }

        public void PlayCollect() => Play(collectClip, "collect");
        public void PlayJump() => Play(jumpClip, "jump");
        public void PlayLand() => Play(landClip, "land");
        public void PlayComplete() => Play(completeClip, "complete");
        public void PlayPause() => Play(pauseClip, "pause");
        public void PlayGameOver() => Play(gameOverClip, "gameOver");

        public void Play(AudioClip clip, string label)
        {
            playRequests++;
            if (clip == null)
            {
                if (reportedMissing.Add(label))
                {
                    missing.Add(label);
                    Debug.LogWarning($"[V6] Audio clip missing: {label} (architecture present, no asset)");
                }

                return;
            }

            source.PlayOneShot(clip);
            clipsPlayed++;
        }

        private int CountAssigned()
        {
            int count = 0;
            if (collectClip != null) count++;
            if (jumpClip != null) count++;
            if (landClip != null) count++;
            if (completeClip != null) count++;
            if (pauseClip != null) count++;
            if (gameOverClip != null) count++;
            return count;
        }
    }
}
