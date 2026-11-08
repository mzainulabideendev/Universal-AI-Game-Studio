using UnityEngine;

namespace V6
{
    /// <summary>Tracks the furthest reached checkpoint and the safe respawn.</summary>
    public class CheckpointManager : MonoBehaviour
    {
        [SerializeField] private Checkpoint[] checkpoints;
        [SerializeField] private LevelManager level;

        private int highestIndex = -1;
        private Vector3 respawn;

        public int HighestIndex => highestIndex;
        public Vector3 RespawnPosition => respawn;
        public int CheckpointCount => checkpoints != null ? checkpoints.Length : 0;

        public void Initialize(LevelManager levelManager)
        {
            level = levelManager;
            var found = FindObjectsByType<Checkpoint>(FindObjectsSortMode.None);
            System.Array.Sort(found, (a, b) => a.Index.CompareTo(b.Index));
            checkpoints = found;
            if (checkpoints != null)
            {
                for (int i = 0; i < checkpoints.Length; i++)
                {
                    if (checkpoints[i] != null)
                    {
                        checkpoints[i].Configure(i, this);
                    }
                }
            }

            ResetCheckpoints();
        }

        public void Initialize(LevelManager levelManager, Checkpoint[] orderedCheckpoints)
        {
            level = levelManager;
            checkpoints = orderedCheckpoints;
            if (checkpoints != null)
            {
                for (int i = 0; i < checkpoints.Length; i++)
                {
                    if (checkpoints[i] != null)
                    {
                        checkpoints[i].Configure(i, this);
                    }
                }
            }

            ResetCheckpoints();
        }

        public void ResetCheckpoints()
        {
            highestIndex = -1;
            respawn = level != null ? level.SpawnPosition : Vector3.zero;
        }

        public void Register(Checkpoint checkpoint)
        {
            if (checkpoint == null || checkpoint.Index <= highestIndex)
            {
                return;
            }

            highestIndex = checkpoint.Index;
            respawn = checkpoint.RespawnPosition;
            Debug.Log($"[V6] Checkpoint {highestIndex} reached");
        }

        public void RegisterByIndex(int index, Vector3 position)
        {
            if (index <= highestIndex)
            {
                return;
            }

            highestIndex = index;
            respawn = position;
            Debug.Log($"[V6] Checkpoint {highestIndex} reached");
        }
    }
}
