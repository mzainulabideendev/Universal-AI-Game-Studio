using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using UnityEditor;
using UnityEditor.Animations;
using UnityEditor.SceneManagement;
using UnityEngine;
using UnityEngine.SceneManagement;
using UnityEngine.UI;

namespace V5.EditorTools
{
    public static class V5SceneBuilder
    {
        private const string Art = "Assets/V5/Art";
        private const string Materials = "Assets/V5/Materials";
        private const string Animations = "Assets/V5/Animations";
        private const string Prefabs = "Assets/V5/Prefabs";
        private const string Scenes = "Assets/V5/Scenes";
        private const string ScenePath = Scenes + "/JungleMonkey.unity";

        public static void BuildScene()
        {
            EnsureFolder(Materials);
            EnsureFolder(Animations);
            EnsureFolder(Prefabs);
            EnsureFolder(Scenes);

            ConfigureModel(Art + "/Monkey.fbx", animated: true);
            ConfigureModel(Art + "/Jungle.fbx", animated: false);
            ConfigureModel(Art + "/Banana.fbx", animated: false);

            var monkeyPrefab = AssetDatabase.LoadAssetAtPath<GameObject>(Art + "/Monkey.fbx");
            var junglePrefab = AssetDatabase.LoadAssetAtPath<GameObject>(Art + "/Jungle.fbx");
            var bananaPrefab = AssetDatabase.LoadAssetAtPath<GameObject>(Art + "/Banana.fbx");
            Require(monkeyPrefab, "Monkey.fbx");
            Require(junglePrefab, "Jungle.fbx");
            Require(bananaPrefab, "Banana.fbx");

            var palette = BuildPalette();
            var controllerAsset = BuildAnimatorController();

            var scene = EditorSceneManager.NewScene(NewSceneSetup.EmptyScene, NewSceneMode.Single);

            RenderSettings.ambientMode = UnityEngine.Rendering.AmbientMode.Trilight;
            RenderSettings.ambientSkyColor = new Color(0.55f, 0.70f, 0.85f);
            RenderSettings.ambientEquatorColor = new Color(0.36f, 0.48f, 0.36f);
            RenderSettings.ambientGroundColor = new Color(0.15f, 0.20f, 0.12f);
            RenderSettings.fog = true;
            RenderSettings.fogColor = new Color(0.55f, 0.68f, 0.62f);
            RenderSettings.fogMode = FogMode.Linear;
            RenderSettings.fogStartDistance = 45f;
            RenderSettings.fogEndDistance = 120f;

            var sun = new GameObject("Sun");
            var light = sun.AddComponent<Light>();
            light.type = LightType.Directional;
            light.color = new Color(1f, 0.96f, 0.86f);
            light.intensity = 1.25f;
            light.shadows = LightShadows.Soft;
            sun.transform.rotation = Quaternion.Euler(42f, -38f, 0f);

            var environment = (GameObject)PrefabUtility.InstantiatePrefab(junglePrefab);
            environment.name = "JungleEnvironment";
            environment.transform.position = Vector3.zero;
            ApplyPalette(environment, palette);
            AddMeshColliders(environment);

            var bananaInstance = (GameObject)PrefabUtility.InstantiatePrefab(bananaPrefab);
            bananaInstance.name = "Banana";
            ApplyPalette(bananaInstance, palette);
            var bananaCollider = bananaInstance.AddComponent<SphereCollider>();
            bananaCollider.isTrigger = true;
            bananaCollider.radius = 0.55f;
            bananaInstance.AddComponent<BananaCollectible>();
            var bananaAsset = PrefabUtility.SaveAsPrefabAsset(bananaInstance, Prefabs + "/Banana.prefab");
            UnityEngine.Object.DestroyImmediate(bananaInstance);

            var player = new GameObject("Player");
            player.tag = "Player";
            player.transform.position = new Vector3(0f, 0.15f, 0f);
            var character = player.AddComponent<CharacterController>();
            character.height = 1.8f;
            character.radius = 0.36f;
            character.center = new Vector3(0f, 0.9f, 0f);
            character.slopeLimit = 50f;
            character.stepOffset = 0.35f;

            var monkey = (GameObject)PrefabUtility.InstantiatePrefab(monkeyPrefab);
            monkey.name = "MonkeyModel";
            monkey.transform.SetParent(player.transform, false);
            monkey.transform.localPosition = Vector3.zero;
            monkey.transform.localRotation = Quaternion.identity;
            monkey.transform.localScale = Vector3.one;
            ApplyPalette(monkey, palette);

            var animator = monkey.GetComponentInChildren<Animator>();
            if (animator == null)
            {
                animator = monkey.AddComponent<Animator>();
            }
            animator.runtimeAnimatorController = controllerAsset;
            animator.applyRootMotion = false;
            animator.cullingMode = AnimatorCullingMode.AlwaysAnimate;

            var monkeyController = player.AddComponent<MonkeyController>();
            player.AddComponent<V5DemoDriver>();

            var cameraObject = new GameObject("Main Camera");
            cameraObject.tag = "MainCamera";
            var camera = cameraObject.AddComponent<Camera>();
            camera.fieldOfView = 62f;
            camera.nearClipPlane = 0.1f;
            camera.farClipPlane = 250f;
            camera.clearFlags = CameraClearFlags.Skybox;
            cameraObject.AddComponent<AudioListener>();
            var follow = cameraObject.AddComponent<CameraFollow>();
            follow.offset = new Vector3(0f, 4.4f, -8.8f);
            follow.SetTarget(player.transform);
            monkeyController.SetCamera(cameraObject.transform);

            var hud = BuildHud();

            var managerObject = new GameObject("GameManager");
            var manager = managerObject.AddComponent<GameManager>();
            var positions = new[]
            {
                new Vector3(0f, 0.85f, 4f),
                new Vector3(4f, 0.85f, 1f),
                new Vector3(-4f, 0.85f, 3f),
                new Vector3(6f, 0.85f, 7f),
                new Vector3(-6f, 0.85f, -4f),
                new Vector3(2f, 0.85f, -7f),
                new Vector3(9f, 0.85f, 3f),
                new Vector3(-3f, 0.85f, 9f),
                new Vector3(5f, 0.85f, -9f),
                new Vector3(-9f, 0.85f, 6f),
            };
            var bananas = new List<BananaCollectible>();
            foreach (var position in positions)
            {
                var instance = (GameObject)PrefabUtility.InstantiatePrefab(bananaAsset);
                instance.transform.position = position;
                var collectible = instance.GetComponent<BananaCollectible>();
                collectible.manager = manager;
                bananas.Add(collectible);
            }

            manager.Player = player.transform;
            manager.Hud = hud;
            manager.Bananas = bananas.ToArray();
            manager.TotalBananas = bananas.Count;

            EditorSceneManager.SaveScene(scene, ScenePath);
            EditorBuildSettings.scenes = new[] { new EditorBuildSettingsScene(ScenePath, true) };

            PlayerSettings.companyName = "Universal AI Game Studio";
            PlayerSettings.productName = "V5 Jungle Monkey";
            PlayerSettings.defaultScreenWidth = 1280;
            PlayerSettings.defaultScreenHeight = 720;
            PlayerSettings.fullScreenMode = FullScreenMode.Windowed;
            PlayerSettings.runInBackground = true;
            PlayerSettings.colorSpace = ColorSpace.Linear;

            AssetDatabase.SaveAssets();
            AssetDatabase.Refresh();
            Debug.Log($"V5_SCENE_OK scene={ScenePath} bananas={bananas.Count} " +
                      $"clips={string.Join(",", LoadClips(Art + "/Monkey.fbx").Select(c => c.name))}");
        }

        private static HUDController BuildHud()
        {
            var canvasObject = new GameObject("HUD", typeof(Canvas), typeof(CanvasScaler),
                typeof(GraphicRaycaster));
            var canvas = canvasObject.GetComponent<Canvas>();
            canvas.renderMode = RenderMode.ScreenSpaceOverlay;
            var scaler = canvasObject.GetComponent<CanvasScaler>();
            scaler.uiScaleMode = CanvasScaler.ScaleMode.ScaleWithScreenSize;
            scaler.referenceResolution = new Vector2(1280f, 720f);
            scaler.matchWidthOrHeight = 0.5f;

            var hud = canvasObject.AddComponent<HUDController>();
            hud.scoreText = CreateText(canvasObject.transform, "ScoreText",
                new Vector2(0.02f, 0.88f), new Vector2(0.55f, 0.98f), 32,
                TextAnchor.UpperLeft, "Bananas: 0 / 10");
            hud.messageText = CreateText(canvasObject.transform, "MessageText",
                new Vector2(0.15f, 0.55f), new Vector2(0.85f, 0.68f), 34,
                TextAnchor.MiddleCenter, string.Empty);
            hud.messageText.color = new Color(1f, 0.92f, 0.35f);
            hud.messageText.gameObject.SetActive(false);
            hud.helpText = CreateText(canvasObject.transform, "HelpText",
                new Vector2(0.02f, 0.02f), new Vector2(0.98f, 0.10f), 20,
                TextAnchor.LowerLeft,
                "WASD / arrows move  ·  Shift run  ·  Space jump  ·  R restart");
            hud.helpText.color = new Color(0.92f, 0.95f, 0.92f);
            return hud;
        }

        private static Text CreateText(Transform parent, string name, Vector2 anchorMin,
            Vector2 anchorMax, int size, TextAnchor alignment, string content)
        {
            var go = new GameObject(name, typeof(RectTransform), typeof(Text));
            go.transform.SetParent(parent, false);
            var rect = go.GetComponent<RectTransform>();
            rect.anchorMin = anchorMin;
            rect.anchorMax = anchorMax;
            rect.offsetMin = Vector2.zero;
            rect.offsetMax = Vector2.zero;
            var text = go.GetComponent<Text>();
            text.font = Resources.GetBuiltinResource<Font>("LegacyRuntime.ttf");
            if (text.font == null)
            {
                text.font = Resources.GetBuiltinResource<Font>("Arial.ttf");
            }
            text.fontSize = size;
            text.alignment = alignment;
            text.color = Color.white;
            text.text = content;
            text.horizontalOverflow = HorizontalWrapMode.Overflow;
            text.verticalOverflow = VerticalWrapMode.Overflow;
            return text;
        }

        private static AnimatorController BuildAnimatorController()
        {
            var path = Animations + "/Monkey.controller";
            AssetDatabase.DeleteAsset(path);
            var controller = AnimatorController.CreateAnimatorControllerAtPath(path);
            controller.AddParameter("Speed", AnimatorControllerParameterType.Float);
            controller.AddParameter("Grounded", AnimatorControllerParameterType.Bool);
            controller.AddParameter("Jump", AnimatorControllerParameterType.Trigger);

            var clips = LoadClips(Art + "/Monkey.fbx");
            var idle = FindClip(clips, "idle");
            var walk = FindClip(clips, "walk");
            var jump = FindClip(clips, "jump");
            Require(idle, "Idle animation clip");
            Require(walk, "Walk animation clip");
            Require(jump, "Jump animation clip");

            var machine = controller.layers[0].stateMachine;
            var idleState = machine.AddState("Idle");
            idleState.motion = idle;
            var walkState = machine.AddState("Walk");
            walkState.motion = walk;
            var jumpState = machine.AddState("Jump");
            jumpState.motion = jump;
            machine.defaultState = idleState;

            var idleToWalk = idleState.AddTransition(walkState);
            idleToWalk.AddCondition(AnimatorConditionMode.Greater, 0.08f, "Speed");
            idleToWalk.hasExitTime = false;
            idleToWalk.duration = 0.12f;

            var walkToIdle = walkState.AddTransition(idleState);
            walkToIdle.AddCondition(AnimatorConditionMode.Less, 0.08f, "Speed");
            walkToIdle.hasExitTime = false;
            walkToIdle.duration = 0.12f;

            var anyToJump = machine.AddAnyStateTransition(jumpState);
            anyToJump.AddCondition(AnimatorConditionMode.If, 0f, "Jump");
            anyToJump.hasExitTime = false;
            anyToJump.duration = 0.05f;
            anyToJump.canTransitionToSelf = false;

            var jumpToIdle = jumpState.AddTransition(idleState);
            jumpToIdle.hasExitTime = true;
            jumpToIdle.exitTime = 0.85f;
            jumpToIdle.duration = 0.1f;

            EditorUtility.SetDirty(controller);
            AssetDatabase.SaveAssets();
            return controller;
        }

        private static List<AnimationClip> LoadClips(string path)
        {
            return AssetDatabase.LoadAllAssetsAtPath(path)
                .OfType<AnimationClip>()
                .Where(clip => !clip.name.StartsWith("__preview__"))
                .ToList();
        }

        private static AnimationClip FindClip(List<AnimationClip> clips, string token)
        {
            return clips.FirstOrDefault(clip => clip.name.ToLowerInvariant().Contains(token));
        }

        private static void ConfigureModel(string path, bool animated)
        {
            var importer = AssetImporter.GetAtPath(path) as ModelImporter;
            Require(importer, "ModelImporter for " + path);
            importer.animationType = ModelImporterAnimationType.Generic;
            importer.importAnimation = animated;
            importer.importBlendShapes = false;
            importer.importCameras = false;
            importer.importLights = false;
            importer.materialImportMode = ModelImporterMaterialImportMode.ImportStandard;
            importer.SaveAndReimport();
        }

        private static Dictionary<string, Material> BuildPalette()
        {
            var palette = new Dictionary<string, Material>
            {
                ["fur"] = CreateMaterial("MonkeyFur", new Color(0.32f, 0.19f, 0.10f), 0.55f),
                ["muzzle"] = CreateMaterial("MonkeyMuzzle", new Color(0.70f, 0.52f, 0.34f), 0.5f),
                ["eyes"] = CreateMaterial("MonkeyEyes", new Color(0.02f, 0.02f, 0.02f), 0.8f),
                ["ground"] = CreateMaterial("JungleGround", new Color(0.16f, 0.34f, 0.12f), 0.15f),
                ["river"] = CreateMaterial("River", new Color(0.06f, 0.30f, 0.55f), 0.9f),
                ["trunk"] = CreateMaterial("TreeTrunk", new Color(0.28f, 0.16f, 0.08f), 0.1f),
                ["canopy"] = CreateMaterial("Canopy", new Color(0.10f, 0.48f, 0.16f), 0.2f),
                ["rock"] = CreateMaterial("Rock", new Color(0.34f, 0.34f, 0.36f), 0.1f),
                ["banana"] = CreateMaterial("BananaYellow", new Color(0.95f, 0.78f, 0.08f), 0.65f),
                ["tip"] = CreateMaterial("BananaTip", new Color(0.35f, 0.22f, 0.05f), 0.2f),
            };
            return palette;
        }

        private static Material CreateMaterial(string name, Color color, float smoothness)
        {
            var path = Materials + "/" + name + ".mat";
            var material = AssetDatabase.LoadAssetAtPath<Material>(path);
            if (material == null)
            {
                material = new Material(Shader.Find("Standard"));
                AssetDatabase.CreateAsset(material, path);
            }
            material.color = color;
            material.SetFloat("_Glossiness", smoothness);
            EditorUtility.SetDirty(material);
            return material;
        }

        private static void ApplyPalette(GameObject root, Dictionary<string, Material> palette)
        {
            foreach (var renderer in root.GetComponentsInChildren<Renderer>(true))
            {
                var materials = renderer.sharedMaterials;
                for (int index = 0; index < materials.Length; index++)
                {
                    var name = materials[index] != null ? materials[index].name.ToLowerInvariant() : string.Empty;
                    var replacement = MatchMaterial(name, palette);
                    if (replacement != null)
                    {
                        materials[index] = replacement;
                    }
                }
                renderer.sharedMaterials = materials;
            }
        }

        private static Material MatchMaterial(string name, Dictionary<string, Material> palette)
        {
            if (name.Contains("banana") && name.Contains("tip")) return palette["tip"];
            if (name.Contains("banana")) return palette["banana"];
            if (name.Contains("muzzle")) return palette["muzzle"];
            if (name.Contains("eye")) return palette["eyes"];
            if (name.Contains("fur") || name.Contains("monkey")) return palette["fur"];
            if (name.Contains("river") || name.Contains("water")) return palette["river"];
            if (name.Contains("trunk") || name.Contains("tree")) return palette["trunk"];
            if (name.Contains("canopy") || name.Contains("leaf") || name.Contains("bush"))
                return palette["canopy"];
            if (name.Contains("rock")) return palette["rock"];
            if (name.Contains("ground") || name.Contains("terrain")) return palette["ground"];
            return null;
        }

        private static void AddMeshColliders(GameObject root)
        {
            var filters = root.GetComponentsInChildren<MeshFilter>(true);
            foreach (var filter in filters)
            {
                if (filter.sharedMesh == null)
                {
                    continue;
                }
                var host = filter.gameObject;
                if (host.GetComponent<Collider>() == null)
                {
                    var collider = host.AddComponent<MeshCollider>();
                    collider.sharedMesh = filter.sharedMesh;
                    collider.convex = false;
                }
            }
        }

        private static void EnsureFolder(string path)
        {
            if (AssetDatabase.IsValidFolder(path))
            {
                return;
            }
            var parent = Path.GetDirectoryName(path).Replace("\\", "/");
            var leaf = Path.GetFileName(path);
            if (!AssetDatabase.IsValidFolder(parent))
            {
                EnsureFolder(parent);
            }
            AssetDatabase.CreateFolder(parent, leaf);
        }

        private static void Require(UnityEngine.Object value, string label)
        {
            if (value == null)
            {
                throw new InvalidOperationException("Missing required asset: " + label);
            }
        }
    }
}
