using System;
using System.IO;
using UnityEngine;

namespace V6
{
    [Serializable]
    public class SaveData
    {
        public int version = 1;
        public int bestScore;
        public bool jungleLevelCompleted;
        public int totalRuns;
        public int totalBananasCollected;
        public float masterVolume = 1f;
        public float mouseSensitivity = 1f;
        public string lastSavedUtc = string.Empty;
    }

    /// <summary>
    /// Local-only, versioned save data. Missing files return defaults, corrupt
    /// files are moved aside and replaced by defaults, and values are clamped
    /// after load. Nothing is uploaded and no credentials are stored.
    /// </summary>
    public class SaveDataService : MonoBehaviour
    {
        public const int CurrentVersion = 1;

        [SerializeField] private string fileName = "v6-save.json";

        public string LastStatus { get; private set; } = "not-loaded";
        public string LastError { get; private set; } = string.Empty;
        public string FilePath =>
            string.IsNullOrEmpty(OverridePath)
                ? Path.Combine(Application.persistentDataPath, fileName)
                : OverridePath;

        /// <summary>Test/diagnostic hook. Leave null in normal play.</summary>
        public string OverridePath { get; set; }

        [Serializable]
        public class ValidationReport
        {
            public bool valid;
            public bool repaired;
            public string[] issues;
        }

        public SaveData Load()
        {
            string path = FilePath;
            LastError = string.Empty;
            if (!File.Exists(path))
            {
                LastStatus = "missing";
                return Defaults();
            }

            try
            {
                string json = File.ReadAllText(path);
                SaveData data = JsonUtility.FromJson<SaveData>(json);
                if (data == null)
                {
                    return RecoverCorrupt(path, "null payload");
                }

                if (data.version != CurrentVersion)
                {
                    LastStatus = "unsupported-version";
                    Quarantine(path, "version-" + data.version);
                    return Defaults();
                }

                data.bestScore = Mathf.Max(0, data.bestScore);
                data.totalRuns = Mathf.Max(0, data.totalRuns);
                data.totalBananasCollected = Mathf.Max(0, data.totalBananasCollected);
                data.masterVolume = Mathf.Clamp01(data.masterVolume);
                data.mouseSensitivity = Mathf.Clamp(data.mouseSensitivity, 0.2f, 3f);
                LastStatus = "loaded";
                return data;
            }
            catch (Exception exception)
            {
                LastError = exception.Message;
                return RecoverCorrupt(path, exception.Message);
            }
        }

        public bool Save(SaveData data)
        {
            if (data == null)
            {
                LastStatus = "save-null";
                return false;
            }

            data.version = CurrentVersion;
            data.bestScore = Mathf.Max(0, data.bestScore);
            data.totalRuns = Mathf.Max(0, data.totalRuns);
            data.totalBananasCollected = Mathf.Max(0, data.totalBananasCollected);
            data.masterVolume = Mathf.Clamp01(data.masterVolume);
            data.mouseSensitivity = Mathf.Clamp(data.mouseSensitivity, 0.2f, 3f);
            data.lastSavedUtc = DateTime.UtcNow.ToString("o");

            string path = FilePath;
            string temp = path + ".tmp";
            try
            {
                string directory = Path.GetDirectoryName(path);
                if (!string.IsNullOrEmpty(directory))
                {
                    Directory.CreateDirectory(directory);
                }

                File.WriteAllText(temp, JsonUtility.ToJson(data, true));
                if (File.Exists(path))
                {
                    File.Delete(path);
                }

                File.Move(temp, path);
                LastStatus = "saved";
                return true;
            }
            catch (Exception exception)
            {
                LastError = exception.Message;
                LastStatus = "save-failed";
                try
                {
                    if (File.Exists(temp))
                    {
                        File.Delete(temp);
                    }
                }
                catch
                {
                    // Best effort cleanup only.
                }

                return false;
            }
        }

        public static SaveData Defaults()
        {
            return new SaveData
            {
                version = CurrentVersion,
                bestScore = 0,
                jungleLevelCompleted = false,
                totalRuns = 0,
                totalBananasCollected = 0,
                masterVolume = 1f,
                mouseSensitivity = 1f,
            };
        }

        public ValidationReport Validate(SaveData data)
        {
            if (data == null)
            {
                return new ValidationReport { valid = false, issues = new[] { "null" } };
            }

            var issues = new System.Collections.Generic.List<string>();
            bool repaired = false;
            if (data.version != CurrentVersion)
            {
                issues.Add("version");
                data.version = CurrentVersion;
                repaired = true;
            }

            if (data.bestScore < 0)
            {
                issues.Add("bestScore");
                data.bestScore = 0;
                repaired = true;
            }

            if (data.masterVolume < 0f || data.masterVolume > 1f)
            {
                issues.Add("masterVolume");
                data.masterVolume = Mathf.Clamp01(data.masterVolume);
                repaired = true;
            }

            if (data.mouseSensitivity < 0.2f || data.mouseSensitivity > 3f)
            {
                issues.Add("mouseSensitivity");
                data.mouseSensitivity = Mathf.Clamp(data.mouseSensitivity, 0.2f, 3f);
                repaired = true;
            }

            return new ValidationReport
            {
                valid = !repaired,
                repaired = repaired,
                issues = issues.ToArray(),
            };
        }

        private SaveData RecoverCorrupt(string path, string reason)
        {
            LastStatus = "corrupt";
            LastError = reason;
            Quarantine(path, "corrupt");
            Debug.LogWarning($"[V6] Save data corrupt ({reason}); using safe defaults. File preserved as backup.");
            return Defaults();
        }

        private void Quarantine(string path, string tag)
        {
            try
            {
                if (!File.Exists(path))
                {
                    return;
                }

                string backup = path + "." + tag + "-" + DateTime.UtcNow.ToString("yyyyMMddTHHmmssZ");
                File.Move(path, backup);
            }
            catch (Exception exception)
            {
                LastError = exception.Message;
            }
        }
    }
}
