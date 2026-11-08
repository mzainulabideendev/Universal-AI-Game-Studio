using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using UnityEditor;
using UnityEditor.Animations;
using UnityEditor.SceneManagement;
using UnityEngine;
using UnityEngine.EventSystems;
using UnityEngine.Rendering;
using UnityEngine.SceneManagement;
using UnityEngine.UI;

namespace V6.EditorTools
{
    /// <summary>
    /// Builds the Phase 5 playable scene from the real Phase 3 character and
    /// Phase 4 environment exports. All references are created here so the
    /// scene is reproducible from the exported FBX/PNG artifacts.
    /// </summary>
    public static class V6SceneBuilder
    {
        private const string Art = "Assets/V6/Art";
        private const string Materials = "Assets/V6/Materials";
        private const string Animations = "Assets/V6/Animations";
        private const string Prefabs = "Assets/V6/Prefabs";
        private const string Scenes = "Assets/V6/Scenes";
        private const string ScenePath = Scenes + "/JungleMonkeyV6.unity";
        private const int PlayerLayer = 8;

        [MenuItem("V6/Build Playable Scene")]
        public static void BuildScene()
        {
            EnsureFolder(Materials);
            EnsureFolder(Animations);
            EnsureFolder(Prefabs);
            EnsureFolder(Scenes);

            ConfigureModel(Art + "/JungleMonkey.fbx", true);
            ConfigureModel(Art + "/JungleLevel.fbx", false);
            ConfigureModel(Art + "/Banana.fbx", false);
            ConfigureTextures();

            var palette = BuildPalette();
            var controller = BuildAnimatorController();

            var scene = EditorSceneManager.NewScene(NewSceneSetup.EmptyScene, NewSceneMode.Single);
            ConfigureLighting();

            var sun = new GameObject("Sun");
            var light = sun.AddComponent<Light>();
            light.type = LightType.Directional;
            light.color = new Color(1f, 0.96f, 0.86f);
            light.intensity = 1.25f;
            light.shadows = LightShadows.Soft;
            light.shadowStrength = 0.72f;
            sun.transform.rotation = Quaternion.Euler(44f, 52f, 0f);

            var envPrefab = AssetDatabase.LoadAssetAtPath<GameObject>(Art + "/JungleLevel.fbx");
            Require(envPrefab, "JungleLevel.fbx");
            var environment = (GameObject)PrefabUtility.InstantiatePrefab(envPrefab);
            environment.name = "JungleEnvironment";
            environment.transform.position = Vector3.zero;
            environment.transform.rotation = Quaternion.identity;
            RemoveImportedDuplicates(environment);
            ApplyPalette(environment, palette);
            AddEnvironmentColliders(environment);
            ConfigureEnvironmentShadows(environment);

            Transform spawnAnchor = FindDeep(environment.transform, "SPAWN_PLAYER");
            Transform ruinAnchor = FindDeep(environment.transform, "RuinPlatform_0");
            Transform destinationAnchor = null;
            var volumes = new GameObject("GameplayVolumes");
            if (ruinAnchor != null)
            {
                var destinationObject = new GameObject("DestinationAnchor");
                destinationObject.transform.SetParent(volumes.transform, false);
                destinationObject.transform.position = ruinAnchor.position + Vector3.up * 0.6f;
                destinationAnchor = destinationObject.transform;
            }

            if (spawnAnchor == null)
            {
                var fallback = new GameObject("SpawnAnchor");
                fallback.transform.SetParent(volumes.transform, false);
                fallback.transform.position = new Vector3(0f, 4f, 48f);
                spawnAnchor = fallback.transform;
            }

            var player = BuildPlayer(spawnAnchor, destinationAnchor, controller, palette);
            var cameraObject = BuildCamera(player.transform);

            var bananaPrefab = BuildBananaPrefab(palette);
            var collectibles = PlaceCollectibles(bananaPrefab, environment.transform, destinationAnchor, volumes.transform);

            var checkpoints = BuildCheckpoints(environment.transform, volumes.transform);

            var destination = BuildDestination(destinationAnchor, volumes.transform);

            var ui = BuildUi();

            var systems = new GameObject("GameSystems");
            var states = systems.AddComponent<GameStateController>();
            var score = systems.AddComponent<ScoreManager>();
            var objectives = systems.AddComponent<ObjectiveManager>();
            var level = systems.AddComponent<LevelManager>();
            var checkpointManager = systems.AddComponent<CheckpointManager>();
            var audio = systems.AddComponent<AudioManager>();
            var save = systems.AddComponent<SaveDataService>();
            var performance = systems.AddComponent<PerformanceMonitor>();
            var collectibleManager = systems.AddComponent<CollectibleManager>();
            var manager = systems.AddComponent<GameManager>();
            var bootstrap = systems.AddComponent<GameBootstrap>();

            level.Configure(spawnAnchor, destinationAnchor);
            collectibleManager.Configure(collectibles.ToArray());

            manager.States = states;
            manager.Score = score;
            manager.Objectives = objectives;
            manager.Level = level;
            manager.Checkpoints = checkpointManager;
            manager.Audio = audio;
            manager.Save = save;
            manager.Performance = performance;
            manager.Collectibles = collectibleManager;
            manager.UI = ui;
            manager.Player = player.GetComponent<PlayerMovement>();
            manager.InputHandler = player.GetComponent<PlayerInputHandler>();
            manager.AnimationDriver = player.GetComponent<PlayerAnimationDriver>();
            manager.CollisionHandler = player.GetComponent<PlayerCollisionHandler>();
            manager.FollowCamera = cameraObject.GetComponent<CameraFollowController>();
            manager.Destination = destination;
            bootstrap.Configure(manager, environment);

            EditorSceneManager.SaveScene(scene, ScenePath);
            EditorBuildSettings.scenes = new[] { new EditorBuildSettingsScene(ScenePath, true) };

            ConfigurePlayerSettings();
            AssetDatabase.SaveAssets();
            AssetDatabase.Refresh();

            var report = ValidateSceneAsset();
            Debug.Log("V6_SCENE_OK " + JsonUtility.ToJson(report));
        }

        private static void ConfigureLighting()
        {
            RenderSettings.ambientMode = AmbientMode.Trilight;
            RenderSettings.ambientSkyColor = new Color(0.46f, 0.62f, 0.78f);
            RenderSettings.ambientEquatorColor = new Color(0.34f, 0.44f, 0.32f);
            RenderSettings.ambientGroundColor = new Color(0.13f, 0.18f, 0.11f);
            RenderSettings.fog = true;
            RenderSettings.fogColor = new Color(0.55f, 0.68f, 0.66f);
            RenderSettings.fogMode = FogMode.Linear;
            RenderSettings.fogStartDistance = 42f;
            RenderSettings.fogEndDistance = 135f;
        }

        private static GameObject BuildPlayer(Transform spawn, Transform destination,
            RuntimeAnimatorController controller, Dictionary<string, Material> palette)
        {
            var player = new GameObject("Player");
            player.tag = "Player";
            player.layer = PlayerLayer;
            player.transform.position = spawn.position + Vector3.up * 0.1f;
            Vector3 facing = destination != null
                ? destination.position - player.transform.position
                : new Vector3(0f, 0f, -1f);
            facing.y = 0f;
            player.transform.rotation = facing.sqrMagnitude > 0.01f
                ? Quaternion.LookRotation(facing.normalized, Vector3.up)
                : Quaternion.identity;

            var character = player.AddComponent<CharacterController>();
            character.height = 1.7f;
            character.radius = 0.32f;
            character.center = new Vector3(0f, 0.85f, 0f);
            character.slopeLimit = 46f;
            character.stepOffset = 0.32f;
            character.skinWidth = 0.02f;
            character.minMoveDistance = 0f;

            var characterPrefab = AssetDatabase.LoadAssetAtPath<GameObject>(Art + "/JungleMonkey.fbx");
            Require(characterPrefab, "JungleMonkey.fbx");
            var model = (GameObject)PrefabUtility.InstantiatePrefab(characterPrefab);
            model.name = "MonkeyModel";
            model.transform.SetParent(player.transform, false);
            model.transform.localPosition = Vector3.zero;
            model.transform.localRotation = Quaternion.identity;
            model.transform.localScale = Vector3.one;
            ApplyPalette(model, palette);
            SetLayerRecursively(model, PlayerLayer);

            var animator = model.GetComponentInChildren<Animator>();
            if (animator == null)
            {
                animator = model.AddComponent<Animator>();
            }

            animator.runtimeAnimatorController = controller;
            animator.applyRootMotion = false;
            animator.cullingMode = AnimatorCullingMode.AlwaysAnimate;

            player.AddComponent<PlayerInputHandler>();
            player.AddComponent<PlayerMovement>();
            player.AddComponent<PlayerAnimationDriver>();
            player.AddComponent<PlayerCollisionHandler>();
            return player;
        }

        private static GameObject BuildCamera(Transform player)
        {
            var cameraObject = new GameObject("Main Camera");
            cameraObject.tag = "MainCamera";
            var camera = cameraObject.AddComponent<Camera>();
            camera.fieldOfView = 62f;
            camera.nearClipPlane = 0.1f;
            camera.farClipPlane = 260f;
            camera.clearFlags = CameraClearFlags.SolidColor;
            camera.backgroundColor = new Color(0.43f, 0.62f, 0.80f);
            camera.allowHDR = false;
            cameraObject.AddComponent<AudioListener>();
            var follow = cameraObject.AddComponent<CameraFollowController>();
            follow.SetTarget(player);
            cameraObject.transform.position = player.position + new Vector3(0f, 4.2f, 8f);
            return cameraObject;
        }

        private static GameObject BuildBananaPrefab(Dictionary<string, Material> palette)
        {
            var bananaPrefab = AssetDatabase.LoadAssetAtPath<GameObject>(Art + "/Banana.fbx");
            Require(bananaPrefab, "Banana.fbx");
            var instance = (GameObject)PrefabUtility.InstantiatePrefab(bananaPrefab);
            instance.name = "Banana";
            var bananaMaterial = palette["banana"];
            foreach (var renderer in instance.GetComponentsInChildren<Renderer>(true))
            {
                var materials = renderer.sharedMaterials;
                for (int i = 0; i < materials.Length; i++)
                {
                    materials[i] = bananaMaterial;
                }

                renderer.sharedMaterials = materials;
            }

            var collider = instance.AddComponent<SphereCollider>();
            collider.isTrigger = true;
            collider.radius = 0.55f;
            instance.AddComponent<Collectible>();
            var asset = PrefabUtility.SaveAsPrefabAsset(instance, Prefabs + "/Banana.prefab");
            UnityEngine.Object.DestroyImmediate(instance);
            Require(asset, "Banana prefab");
            return asset;
        }

        private static List<Collectible> PlaceCollectibles(GameObject bananaPrefab, Transform environment,
            Transform destination, Transform parent)
        {
            var positions = new List<Vector3>();
            for (int i = 0; i <= 8; i++)
            {
                Transform waypoint = FindDeep(environment, $"ROUTE_WAYPOINT_{i:00}");
                if (waypoint != null)
                {
                    positions.Add(waypoint.position);
                }
            }

            if (positions.Count == 0)
            {
                positions.AddRange(new[]
                {
                    new Vector3(0f, 3f, 40f), new Vector3(0f, 3f, 28f),
                    new Vector3(0f, 3f, 16f), new Vector3(0f, 3f, 4f),
                    new Vector3(0f, 3f, -8f),
                });
            }

            if (destination != null && positions.Count > 0)
            {
                Vector3 last = positions[positions.Count - 1];
                positions.Add(Vector3.Lerp(last, destination.position, 0.62f));
            }

            while (positions.Count < 10)
            {
                int index = positions.Count;
                positions.Add(new Vector3(index * 0.6f - 3f, 3f, -42f));
            }

            var list = new List<Collectible>();
            var holder = new GameObject("Collectibles");
            holder.transform.SetParent(parent, false);
            for (int i = 0; i < 10; i++)
            {
                var instance = (GameObject)PrefabUtility.InstantiatePrefab(bananaPrefab);
                instance.name = $"Banana_{i:00}";
                instance.transform.SetParent(holder.transform, true);
                instance.transform.position = positions[i];
                list.Add(instance.GetComponent<Collectible>());
            }

            return list;
        }

        private static List<Checkpoint> BuildCheckpoints(Transform environment, Transform parent)
        {
            var list = new List<Checkpoint>();
            var holder = new GameObject("Checkpoints");
            holder.transform.SetParent(parent, false);
            int[] waypointIndices = { 3, 6 };
            for (int i = 0; i < waypointIndices.Length; i++)
            {
                Transform waypoint = FindDeep(environment, $"ROUTE_WAYPOINT_{waypointIndices[i]:00}");
                if (waypoint == null)
                {
                    continue;
                }

                var go = new GameObject($"Checkpoint_{i:00}");
                go.transform.SetParent(holder.transform, false);
                go.transform.position = waypoint.position + Vector3.up * 0.9f;
                var sphere = go.AddComponent<SphereCollider>();
                sphere.isTrigger = true;
                sphere.radius = 2.6f;
                var checkpoint = go.AddComponent<Checkpoint>();
                checkpoint.Configure(list.Count, null);
                list.Add(checkpoint);
            }

            return list;
        }

        private static DestinationZone BuildDestination(Transform destination, Transform parent)
        {
            var go = new GameObject("DestinationZone");
            go.transform.SetParent(parent, false);
            go.transform.position = destination != null
                ? destination.position
                : new Vector3(0f, 2.2f, -46f);
            var sphere = go.AddComponent<SphereCollider>();
            sphere.isTrigger = true;
            sphere.radius = 3.2f;
            return go.AddComponent<DestinationZone>();
        }

        private static UIManager BuildUi()
        {
            var eventSystem = new GameObject("EventSystem", typeof(EventSystem), typeof(StandaloneInputModule));

            var canvasObject = new GameObject("HUD", typeof(Canvas), typeof(CanvasScaler), typeof(GraphicRaycaster));
            var canvas = canvasObject.GetComponent<Canvas>();
            canvas.renderMode = RenderMode.ScreenSpaceOverlay;
            canvas.sortingOrder = 10;
            var scaler = canvasObject.GetComponent<CanvasScaler>();
            scaler.uiScaleMode = CanvasScaler.ScaleMode.ScaleWithScreenSize;
            scaler.referenceResolution = new Vector2(1920f, 1080f);
            scaler.screenMatchMode = CanvasScaler.ScreenMatchMode.MatchWidthOrHeight;
            scaler.matchWidthOrHeight = 0.5f;

            var ui = canvasObject.AddComponent<UIManager>();

            var hud = CreatePanel(canvasObject.transform, "HUDGroup", new Color(0f, 0f, 0f, 0f),
                Vector2.zero, Vector2.one);
            ui.hudGroup = hud;

            ui.bananaText = CreateText(hud.transform, "BananaText", "BANANAS  0 / 10", 38,
                new Vector2(0.025f, 0.90f), new Vector2(0.34f, 0.975f), TextAnchor.UpperLeft,
                new Color(1f, 0.93f, 0.55f), true);
            ui.objectiveText = CreateText(hud.transform, "ObjectiveText", "OBJECTIVE", 27,
                new Vector2(0.30f, 0.905f), new Vector2(0.74f, 0.97f), TextAnchor.MiddleCenter,
                Color.white, true);
            ui.bestText = CreateText(hud.transform, "BestText", "BEST  0", 23,
                new Vector2(0.55f, 0.845f), new Vector2(0.74f, 0.90f), TextAnchor.MiddleRight,
                new Color(0.86f, 0.94f, 0.86f), true);
            ui.helpText = CreateText(hud.transform, "HelpText",
                "WASD / arrows move   ·   Shift run   ·   Space jump   ·   Mouse orbit   ·   Escape pause   ·   R restart",
                20, new Vector2(0.025f, 0.02f), new Vector2(0.75f, 0.075f), TextAnchor.LowerLeft,
                new Color(0.92f, 0.96f, 0.92f), true);

            ui.pauseButton = CreateButton(hud.transform, "PauseButton", "PAUSE",
                new Vector2(0.865f, 0.90f), new Vector2(0.975f, 0.965f),
                new Color(0.12f, 0.30f, 0.15f, 0.95f), 24);
            ui.restartButton = CreateButton(hud.transform, "RestartButton", "RESTART",
                new Vector2(0.865f, 0.825f), new Vector2(0.975f, 0.89f),
                new Color(0.32f, 0.20f, 0.08f, 0.95f), 22);
            ui.toastText = CreateText(hud.transform, "ToastText", string.Empty, 32,
                new Vector2(0.14f, 0.60f), new Vector2(0.86f, 0.71f), TextAnchor.MiddleCenter,
                new Color(1f, 0.91f, 0.35f), true);
            ui.toastText.gameObject.SetActive(false);

            var mainMenu = CreatePanel(canvasObject.transform, "MainMenu", new Color(0.02f, 0.05f, 0.03f, 0.94f),
                Vector2.zero, Vector2.one);
            ui.mainMenuPanel = mainMenu;
            CreateText(mainMenu.transform, "Title", "JUNGLE MONKEY", 84,
                new Vector2(0.08f, 0.70f), new Vector2(0.92f, 0.88f), TextAnchor.MiddleCenter,
                new Color(1f, 0.90f, 0.42f), true).fontStyle = FontStyle.Bold;
            CreateText(mainMenu.transform, "Subtitle", "UNIVERSAL AI GAME STUDIO   ·   V6 PHASE 5", 24,
                new Vector2(0.08f, 0.635f), new Vector2(0.92f, 0.70f), TextAnchor.MiddleCenter,
                new Color(0.75f, 0.90f, 0.78f), false);
            ui.mainMenuBestText = CreateText(mainMenu.transform, "Best", "No completed runs yet", 26,
                new Vector2(0.08f, 0.565f), new Vector2(0.92f, 0.625f), TextAnchor.MiddleCenter,
                Color.white, false);
            CreateText(mainMenu.transform, "Pitch", "Collect 10 bananas, then reach the jungle ruins.", 26,
                new Vector2(0.08f, 0.51f), new Vector2(0.92f, 0.56f), TextAnchor.MiddleCenter,
                new Color(0.90f, 0.95f, 0.88f), false);
            ui.startButton = CreateButton(mainMenu.transform, "StartButton", "START GAME",
                new Vector2(0.38f, 0.34f), new Vector2(0.62f, 0.44f),
                new Color(0.16f, 0.48f, 0.20f, 0.98f), 34);
            CreateText(mainMenu.transform, "Controls",
                "WASD / arrows: move   ·   Shift: run   ·   Space: jump\nMouse: orbit camera   ·   Escape: pause   ·   R: restart",
                22, new Vector2(0.08f, 0.12f), new Vector2(0.92f, 0.26f), TextAnchor.MiddleCenter,
                new Color(0.80f, 0.88f, 0.82f), false);

            var pause = CreatePanel(canvasObject.transform, "PauseMenu", new Color(0f, 0f, 0f, 0.72f),
                Vector2.zero, Vector2.one);
            ui.pausePanel = pause;
            CreateText(pause.transform, "PausedTitle", "PAUSED", 72,
                new Vector2(0.1f, 0.63f), new Vector2(0.9f, 0.78f), TextAnchor.MiddleCenter,
                new Color(1f, 0.92f, 0.45f), true).fontStyle = FontStyle.Bold;
            ui.resumeButton = CreateButton(pause.transform, "ResumeButton", "RESUME",
                new Vector2(0.40f, 0.47f), new Vector2(0.60f, 0.545f),
                new Color(0.16f, 0.48f, 0.20f, 0.98f), 30);
            ui.pauseRestartButton = CreateButton(pause.transform, "PauseRestart", "RESTART",
                new Vector2(0.40f, 0.375f), new Vector2(0.60f, 0.45f),
                new Color(0.36f, 0.24f, 0.08f, 0.98f), 26);
            ui.pauseMenuButton = CreateButton(pause.transform, "PauseMenuButton", "MAIN MENU",
                new Vector2(0.40f, 0.28f), new Vector2(0.60f, 0.355f),
                new Color(0.20f, 0.24f, 0.22f, 0.98f), 26);
            CreateText(pause.transform, "PauseHint", "Escape resumes · R restarts", 22,
                new Vector2(0.1f, 0.18f), new Vector2(0.9f, 0.24f), TextAnchor.MiddleCenter,
                new Color(0.85f, 0.90f, 0.85f), false);

            var gameOver = CreatePanel(canvasObject.transform, "GameOverMenu", new Color(0.12f, 0.01f, 0.01f, 0.88f),
                Vector2.zero, Vector2.one);
            ui.gameOverPanel = gameOver;
            CreateText(gameOver.transform, "GameOverTitle", "GAME OVER", 76,
                new Vector2(0.1f, 0.58f), new Vector2(0.9f, 0.74f), TextAnchor.MiddleCenter,
                new Color(1f, 0.38f, 0.30f), true).fontStyle = FontStyle.Bold;
            ui.gameOverReasonText = CreateText(gameOver.transform, "GameOverReason", string.Empty, 30,
                new Vector2(0.15f, 0.44f), new Vector2(0.85f, 0.56f), TextAnchor.MiddleCenter,
                Color.white, false);
            ui.gameOverRestartButton = CreateButton(gameOver.transform, "GameOverRestart", "RESTART  (R)",
                new Vector2(0.38f, 0.30f), new Vector2(0.62f, 0.39f),
                new Color(0.48f, 0.16f, 0.10f, 0.98f), 30);

            var complete = CreatePanel(canvasObject.transform, "CompleteMenu", new Color(0.01f, 0.14f, 0.05f, 0.88f),
                Vector2.zero, Vector2.one);
            ui.completePanel = complete;
            CreateText(complete.transform, "CompleteTitle", "LEVEL COMPLETE!", 72,
                new Vector2(0.08f, 0.60f), new Vector2(0.92f, 0.75f), TextAnchor.MiddleCenter,
                new Color(0.55f, 1f, 0.55f), true).fontStyle = FontStyle.Bold;
            ui.completeStatsText = CreateText(complete.transform, "CompleteStats", string.Empty, 32,
                new Vector2(0.18f, 0.44f), new Vector2(0.82f, 0.58f), TextAnchor.MiddleCenter,
                Color.white, false);
            ui.completeRestartButton = CreateButton(complete.transform, "CompleteRestart", "PLAY AGAIN  (R)",
                new Vector2(0.37f, 0.30f), new Vector2(0.63f, 0.39f),
                new Color(0.16f, 0.48f, 0.20f, 0.98f), 28);
            ui.completeMenuButton = CreateButton(complete.transform, "CompleteMenu", "MAIN MENU",
                new Vector2(0.40f, 0.20f), new Vector2(0.60f, 0.275f),
                new Color(0.18f, 0.22f, 0.20f, 0.98f), 24);

            mainMenu.SetActive(false);
            pause.SetActive(false);
            gameOver.SetActive(false);
            complete.SetActive(false);
            return ui;
        }

        private static GameObject CreatePanel(Transform parent, string name, Color color,
            Vector2 anchorMin, Vector2 anchorMax)
        {
            var go = new GameObject(name, typeof(RectTransform), typeof(Image));
            go.transform.SetParent(parent, false);
            var rect = go.GetComponent<RectTransform>();
            rect.anchorMin = anchorMin;
            rect.anchorMax = anchorMax;
            rect.offsetMin = Vector2.zero;
            rect.offsetMax = Vector2.zero;
            var image = go.GetComponent<Image>();
            image.color = color;
            image.raycastTarget = color.a > 0.01f;
            return go;
        }

        private static Text CreateText(Transform parent, string name, string content, int size,
            Vector2 anchorMin, Vector2 anchorMax, TextAnchor alignment, Color color, bool outline)
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
            text.color = color;
            text.text = content;
            text.horizontalOverflow = HorizontalWrapMode.Wrap;
            text.verticalOverflow = VerticalWrapMode.Overflow;
            text.raycastTarget = false;
            if (outline)
            {
                var shadow = go.AddComponent<Shadow>();
                shadow.effectColor = new Color(0f, 0f, 0f, 0.72f);
                shadow.effectDistance = new Vector2(1.6f, -1.6f);
            }

            return text;
        }

        private static Button CreateButton(Transform parent, string name, string label,
            Vector2 anchorMin, Vector2 anchorMax, Color color, int fontSize)
        {
            var go = new GameObject(name, typeof(RectTransform), typeof(Image), typeof(Button));
            go.transform.SetParent(parent, false);
            var rect = go.GetComponent<RectTransform>();
            rect.anchorMin = anchorMin;
            rect.anchorMax = anchorMax;
            rect.offsetMin = Vector2.zero;
            rect.offsetMax = Vector2.zero;
            var image = go.GetComponent<Image>();
            image.color = color;
            var button = go.GetComponent<Button>();
            button.targetGraphic = image;
            var colors = button.colors;
            colors.normalColor = Color.white;
            colors.highlightedColor = new Color(1.12f, 1.12f, 1.12f, 1f);
            colors.pressedColor = new Color(0.82f, 0.82f, 0.82f, 1f);
            colors.disabledColor = new Color(0.45f, 0.45f, 0.45f, 0.65f);
            button.colors = colors;
            var text = CreateText(go.transform, "Label", label, fontSize,
                new Vector2(0.04f, 0.06f), new Vector2(0.96f, 0.94f), TextAnchor.MiddleCenter,
                Color.white, false);
            text.fontStyle = FontStyle.Bold;
            return button;
        }

        private static AnimatorController BuildAnimatorController()
        {
            string path = Animations + "/V6Monkey.controller";
            AssetDatabase.DeleteAsset(path);
            var controller = AnimatorController.CreateAnimatorControllerAtPath(path);
            controller.AddParameter("Speed", AnimatorControllerParameterType.Float);
            controller.AddParameter("Grounded", AnimatorControllerParameterType.Bool);
            controller.AddParameter("VerticalSpeed", AnimatorControllerParameterType.Float);
            controller.AddParameter("Jump", AnimatorControllerParameterType.Trigger);

            var clips = LoadClips(Art + "/JungleMonkey.fbx");
            var idle = FindClip(clips, "idle");
            var walk = FindClip(clips, "walk");
            var run = FindClip(clips, "run");
            var jump = FindClip(clips, "jump");
            Require(idle, "Idle animation clip");
            Require(walk, "Walk animation clip");
            Require(run, "Run animation clip");
            Require(jump, "Jump animation clip");
            ConfigureLoop(idle, true);
            ConfigureLoop(walk, true);
            ConfigureLoop(run, true);
            ConfigureLoop(jump, false);

            var machine = controller.layers[0].stateMachine;
            var idleState = machine.AddState("Idle", new Vector3(220f, 20f, 0f));
            var walkState = machine.AddState("Walk", new Vector3(460f, 20f, 0f));
            var runState = machine.AddState("Run", new Vector3(700f, 20f, 0f));
            var jumpState = machine.AddState("Jump", new Vector3(460f, 170f, 0f));
            idleState.motion = idle;
            walkState.motion = walk;
            runState.motion = run;
            jumpState.motion = jump;
            machine.defaultState = idleState;

            var idleToWalk = idleState.AddTransition(walkState);
            idleToWalk.AddCondition(AnimatorConditionMode.Greater, 0.08f, "Speed");
            idleToWalk.hasExitTime = false;
            idleToWalk.duration = 0.12f;

            var walkToIdle = walkState.AddTransition(idleState);
            walkToIdle.AddCondition(AnimatorConditionMode.Less, 0.07f, "Speed");
            walkToIdle.hasExitTime = false;
            walkToIdle.duration = 0.12f;

            var walkToRun = walkState.AddTransition(runState);
            walkToRun.AddCondition(AnimatorConditionMode.Greater, 0.62f, "Speed");
            walkToRun.hasExitTime = false;
            walkToRun.duration = 0.1f;

            var runToWalk = runState.AddTransition(walkState);
            runToWalk.AddCondition(AnimatorConditionMode.Less, 0.58f, "Speed");
            runToWalk.hasExitTime = false;
            runToWalk.duration = 0.1f;

            var anyToJump = machine.AddAnyStateTransition(jumpState);
            anyToJump.AddCondition(AnimatorConditionMode.If, 0f, "Jump");
            anyToJump.hasExitTime = false;
            anyToJump.duration = 0.05f;
            anyToJump.canTransitionToSelf = false;

            var jumpToIdle = jumpState.AddTransition(idleState);
            jumpToIdle.AddCondition(AnimatorConditionMode.If, 0f, "Grounded");
            jumpToIdle.AddCondition(AnimatorConditionMode.Less, -0.1f, "VerticalSpeed");
            jumpToIdle.hasExitTime = true;
            jumpToIdle.exitTime = 0.55f;
            jumpToIdle.duration = 0.08f;

            EditorUtility.SetDirty(controller);
            AssetDatabase.SaveAssets();
            return controller;
        }

        private static void ConfigureLoop(AnimationClip clip, bool loop)
        {
            if (clip == null)
            {
                return;
            }

            var settings = AnimationUtility.GetAnimationClipSettings(clip);
            settings.loopTime = loop;
            AnimationUtility.SetAnimationClipSettings(clip, settings);
            EditorUtility.SetDirty(clip);
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
            return clips.FirstOrDefault(clip =>
                clip.name.IndexOf(token, StringComparison.OrdinalIgnoreCase) >= 0);
        }

        private static void ConfigureModel(string path, bool animated)
        {
            var importer = AssetImporter.GetAtPath(path) as ModelImporter;
            if (importer == null)
            {
                throw new InvalidOperationException("Missing ModelImporter for " + path);
            }

            importer.animationType = ModelImporterAnimationType.Generic;
            importer.importAnimation = animated;
            importer.importBlendShapes = false;
            importer.importCameras = false;
            importer.importLights = false;
            importer.importNormals = ModelImporterNormals.Import;
            importer.importTangents = ModelImporterTangents.CalculateMikk;
            importer.materialImportMode = ModelImporterMaterialImportMode.ImportStandard;
            importer.isReadable = true;
            importer.SaveAndReimport();
        }

        private static void ConfigureTextures()
        {
            ConfigureTexture(Art + "/T_Monkey_Fur_BaseColor.png", false);
            ConfigureTexture(Art + "/T_Monkey_Fur_Normal.png", true);
            ConfigureTexture(Art + "/T_Monkey_Fur_Roughness.png", false);
            ConfigureTexture(Art + "/T_Env_Ground_BaseColor.png", false);
            ConfigureTexture(Art + "/T_Env_Ground_Normal.png", true);
            ConfigureTexture(Art + "/T_Env_Ground_Roughness.png", false);
        }

        private static void ConfigureTexture(string path, bool normal)
        {
            var importer = AssetImporter.GetAtPath(path) as TextureImporter;
            if (importer == null)
            {
                Debug.LogWarning("[V6] Missing texture importer: " + path);
                return;
            }

            importer.textureType = normal ? TextureImporterType.NormalMap : TextureImporterType.Default;
            importer.sRGBTexture = !normal;
            importer.mipmapEnabled = true;
            importer.maxTextureSize = 1024;
            importer.SaveAndReimport();
        }

        private static Dictionary<string, Material> BuildPalette()
        {
            var baseColor = AssetDatabase.LoadAssetAtPath<Texture2D>(Art + "/T_Monkey_Fur_BaseColor.png");
            var normal = AssetDatabase.LoadAssetAtPath<Texture2D>(Art + "/T_Monkey_Fur_Normal.png");
            var groundColor = AssetDatabase.LoadAssetAtPath<Texture2D>(Art + "/T_Env_Ground_BaseColor.png");
            var groundNormal = AssetDatabase.LoadAssetAtPath<Texture2D>(Art + "/T_Env_Ground_Normal.png");

            var palette = new Dictionary<string, Material>
            {
                ["M_Monkey_Fur"] = CreateMaterial("M_Monkey_Fur", Color.white, 0.32f, baseColor, normal),
                ["M_Monkey_Skin"] = CreateMaterial("M_Monkey_Skin", new Color(0.55f, 0.38f, 0.25f), 0.38f),
                ["M_Monkey_Nose"] = CreateMaterial("M_Monkey_Nose", new Color(0.16f, 0.10f, 0.08f), 0.45f),
                ["M_Monkey_EyeWhite"] = CreateMaterial("M_Monkey_EyeWhite", new Color(0.92f, 0.89f, 0.82f), 0.68f),
                ["M_Monkey_Iris"] = CreateMaterial("M_Monkey_Iris", new Color(0.35f, 0.18f, 0.04f), 0.62f),
                ["M_Monkey_Pupil"] = CreateMaterial("M_Monkey_Pupil", new Color(0.02f, 0.02f, 0.02f), 0.72f),
                ["M_Monkey_InnerEar"] = CreateMaterial("M_Monkey_InnerEar", new Color(0.62f, 0.35f, 0.30f), 0.32f),

                ["M_Env_Leaf"] = CreateMaterial("M_Env_Leaf", new Color(0.10f, 0.28f, 0.07f), 0.18f),
                ["M_Env_Rock"] = CreateMaterial("M_Env_Rock", new Color(0.30f, 0.29f, 0.26f), 0.12f),
                ["M_Env_Wood"] = CreateMaterial("M_Env_Wood", new Color(0.26f, 0.17f, 0.09f), 0.10f),
                ["M_Env_Grass"] = CreateMaterial("M_Env_Grass", new Color(0.16f, 0.31f, 0.08f), 0.12f),
                ["M_Env_Rock_Mossy"] = CreateMaterial("M_Env_Rock_Mossy", new Color(0.22f, 0.27f, 0.16f), 0.10f),
                ["M_Env_Leaf_Light"] = CreateMaterial("M_Env_Leaf_Light", new Color(0.22f, 0.40f, 0.10f), 0.16f),
                ["M_Env_Water"] = CreateWaterMaterial("M_Env_Water", new Color(0.06f, 0.22f, 0.26f, 0.82f)),
                ["M_Env_WetGround"] = CreateMaterial("M_Env_WetGround", new Color(0.13f, 0.14f, 0.08f), 0.42f),
                ["M_Env_Root"] = CreateMaterial("M_Env_Root", new Color(0.20f, 0.13f, 0.07f), 0.08f),
                ["M_Env_Stone"] = CreateMaterial("M_Env_Stone", new Color(0.38f, 0.36f, 0.31f), 0.18f),
                ["M_Env_Ground"] = CreateMaterial("M_Env_Ground", Color.white, 0.20f, groundColor, groundNormal),
                ["M_Env_Bark"] = CreateMaterial("M_Env_Bark", new Color(0.22f, 0.14f, 0.08f), 0.08f),
                ["banana"] = CreateMaterial("BananaYellow", new Color(0.95f, 0.78f, 0.08f), 0.62f),
            };
            return palette;
        }

        private static Material CreateMaterial(string name, Color color, float smoothness,
            Texture2D baseMap = null, Texture2D normalMap = null)
        {
            string path = Materials + "/" + name + ".mat";
            var material = AssetDatabase.LoadAssetAtPath<Material>(path);
            if (material == null)
            {
                material = new Material(Shader.Find("Standard"));
                AssetDatabase.CreateAsset(material, path);
            }

            material.shader = Shader.Find("Standard");
            material.color = color;
            material.SetFloat("_Glossiness", smoothness);
            material.SetFloat("_Metallic", 0f);
            if (baseMap != null)
            {
                material.SetTexture("_MainTex", baseMap);
            }

            if (normalMap != null)
            {
                material.SetTexture("_BumpMap", normalMap);
                material.SetFloat("_BumpScale", 1f);
                material.EnableKeyword("_NORMALMAP");
            }

            EditorUtility.SetDirty(material);
            return material;
        }

        private static Material CreateWaterMaterial(string name, Color color)
        {
            var material = CreateMaterial(name, color, 0.9f);
            material.SetFloat("_Mode", 3f);
            material.SetInt("_SrcBlend", (int)BlendMode.SrcAlpha);
            material.SetInt("_DstBlend", (int)BlendMode.OneMinusSrcAlpha);
            material.SetInt("_ZWrite", 0);
            material.DisableKeyword("_ALPHATEST_ON");
            material.EnableKeyword("_ALPHABLEND_ON");
            material.DisableKeyword("_ALPHAPREMULTIPLY_ON");
            material.renderQueue = 3000;
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
                    var current = materials[index];
                    string name = current != null ? current.name : string.Empty;
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
            if (string.IsNullOrEmpty(name))
            {
                return null;
            }

            string lower = name.ToLowerInvariant();
            foreach (var pair in palette)
            {
                if (lower == pair.Key.ToLowerInvariant())
                {
                    return pair.Value;
                }
            }

            if (lower.Contains("banana")) return palette["banana"];
            if (lower.Contains("muzzle") || lower.Contains("skin")) return palette["M_Monkey_Skin"];
            if (lower.Contains("eye_white") || lower.Contains("eyewhite")) return palette["M_Monkey_EyeWhite"];
            if (lower.Contains("iris")) return palette["M_Monkey_Iris"];
            if (lower.Contains("pupil")) return palette["M_Monkey_Pupil"];
            if (lower.Contains("inner")) return palette["M_Monkey_InnerEar"];
            if (lower.Contains("nose")) return palette["M_Monkey_Nose"];
            if (lower.Contains("fur") || lower.Contains("monkey")) return palette["M_Monkey_Fur"];
            if (lower.Contains("water") || lower.Contains("river")) return palette["M_Env_Water"];
            if (lower.Contains("bark") || lower.Contains("trunk") || lower.Contains("wood")) return palette["M_Env_Wood"];
            if (lower.Contains("moss")) return palette["M_Env_Rock_Mossy"];
            if (lower.Contains("leaf_light")) return palette["M_Env_Leaf_Light"];
            if (lower.Contains("leaf")) return palette["M_Env_Leaf"];
            if (lower.Contains("grass")) return palette["M_Env_Grass"];
            if (lower.Contains("rock") || lower.Contains("stone")) return palette["M_Env_Rock"];
            if (lower.Contains("root")) return palette["M_Env_Root"];
            if (lower.Contains("wet")) return palette["M_Env_WetGround"];
            if (lower.Contains("ground") || lower.Contains("terrain")) return palette["M_Env_Ground"];
            return null;
        }

        private static void RemoveImportedDuplicates(GameObject environment)
        {
            var toDestroy = new List<GameObject>();
            foreach (var transform in environment.GetComponentsInChildren<Transform>(true))
            {
                if (transform == environment.transform)
                {
                    continue;
                }

                string name = transform.name;
                if (name.IndexOf("JungleMonkey", StringComparison.OrdinalIgnoreCase) >= 0 ||
                    name.StartsWith("CAM_", StringComparison.OrdinalIgnoreCase) ||
                    name.StartsWith("Sun_Key", StringComparison.OrdinalIgnoreCase))
                {
                    toDestroy.Add(transform.gameObject);
                }
            }

            foreach (var go in toDestroy)
            {
                if (go != null)
                {
                    UnityEngine.Object.DestroyImmediate(go);
                }
            }
        }

        private static void AddEnvironmentColliders(GameObject environment)
        {
            int meshColliders = 0;
            int capsules = 0;
            int triggers = 0;
            foreach (var filter in environment.GetComponentsInChildren<MeshFilter>(true))
            {
                if (filter.sharedMesh == null || filter.gameObject.GetComponent<Collider>() != null)
                {
                    continue;
                }

                string lower = filter.gameObject.name.ToLowerInvariant();
                if (lower.StartsWith("bush") || lower.StartsWith("fern") ||
                    lower.StartsWith("grass") || lower.StartsWith("plant") ||
                    lower.StartsWith("roots") || lower.StartsWith("debris"))
                {
                    continue;
                }

                if (lower.Contains("river_water") || lower == "river" || lower.Contains("water"))
                {
                    var water = filter.gameObject.AddComponent<MeshCollider>();
                    water.sharedMesh = filter.sharedMesh;
                    water.isTrigger = true;
                    triggers++;
                    continue;
                }

                if (lower.StartsWith("tree"))
                {
                    var bounds = filter.sharedMesh.bounds;
                    var capsule = filter.gameObject.AddComponent<CapsuleCollider>();
                    capsule.center = bounds.center;
                    capsule.height = Mathf.Max(1.6f, bounds.size.y);
                    capsule.radius = 0.62f;
                    capsules++;
                    continue;
                }

                if (lower.Contains("terrain") || lower.Contains("riverbank") ||
                    lower.Contains("rock") || lower.Contains("log") ||
                    lower.Contains("ruin") || lower.Contains("cube") ||
                    lower.Contains("cylinder"))
                {
                    var collider = filter.gameObject.AddComponent<MeshCollider>();
                    collider.sharedMesh = filter.sharedMesh;
                    collider.convex = false;
                    meshColliders++;
                }
            }

            Debug.Log($"[V6] Environment colliders mesh={meshColliders} capsules={capsules} triggers={triggers}");
        }

        private static void ConfigureEnvironmentShadows(GameObject environment)
        {
            foreach (var renderer in environment.GetComponentsInChildren<Renderer>(true))
            {
                string lower = renderer.gameObject.name.ToLowerInvariant();
                bool decorative = lower.StartsWith("bush") || lower.StartsWith("fern") ||
                                  lower.StartsWith("grass") || lower.StartsWith("plant") ||
                                  lower.Contains("water");
                renderer.shadowCastingMode = decorative ? ShadowCastingMode.Off : ShadowCastingMode.On;
            }
        }

        private static Transform FindDeep(Transform root, string name)
        {
            if (root.name == name)
            {
                return root;
            }

            foreach (Transform child in root)
            {
                var result = FindDeep(child, name);
                if (result != null)
                {
                    return result;
                }
            }

            return null;
        }

        private static void SetLayerRecursively(GameObject target, int layer)
        {
            target.layer = layer;
            foreach (Transform child in target.transform)
            {
                SetLayerRecursively(child.gameObject, layer);
            }
        }

        private static void ConfigurePlayerSettings()
        {
            PlayerSettings.companyName = "Universal AI Game Studio";
            PlayerSettings.productName = "V6 Jungle Monkey";
            PlayerSettings.defaultScreenWidth = 1280;
            PlayerSettings.defaultScreenHeight = 720;
            PlayerSettings.fullScreenMode = FullScreenMode.Windowed;
            PlayerSettings.runInBackground = true;
            PlayerSettings.colorSpace = ColorSpace.Linear;
            PlayerSettings.usePlayerLog = true;

            string[] qualityNames = QualitySettings.names;
            for (int i = 0; i < qualityNames.Length; i++)
            {
                if (qualityNames[i].IndexOf("Medium", StringComparison.OrdinalIgnoreCase) >= 0)
                {
                    QualitySettings.SetQualityLevel(i, true);
                    break;
                }
            }

            QualitySettings.shadowDistance = 45f;
            QualitySettings.shadows = ShadowQuality.All;
            QualitySettings.vSyncCount = 0;
        }

        [Serializable]
        public class SceneBuildReport
        {
            public string scene;
            public int renderers;
            public int missingMaterials;
            public int missingShaders;
            public int meshColliders;
            public int capsuleColliders;
            public int triggerColliders;
            public int collectibles;
            public int checkpoints;
            public string[] animationClips;
            public string[] animatorStates;
            public string[] materials;
            public bool characterImported;
            public bool environmentImported;
            public bool succeeded;
        }

        public static SceneBuildReport ValidateSceneAsset()
        {
            var scene = EditorSceneManager.OpenScene(ScenePath, OpenSceneMode.Single);
            var report = new SceneBuildReport
            {
                scene = ScenePath,
                animationClips = LoadClips(Art + "/JungleMonkey.fbx").Select(c => c.name).ToArray(),
                collectibles = UnityEngine.Object.FindObjectsByType<Collectible>(FindObjectsSortMode.None).Length,
                checkpoints = UnityEngine.Object.FindObjectsByType<Checkpoint>(FindObjectsSortMode.None).Length,
            };

            int missingMaterials = 0;
            int missingShaders = 0;
            int meshColliders = 0;
            int capsuleColliders = 0;
            int triggers = 0;
            var materials = new HashSet<string>();
            foreach (var renderer in UnityEngine.Object.FindObjectsByType<Renderer>(FindObjectsSortMode.None))
            {
                report.renderers++;
                foreach (var material in renderer.sharedMaterials)
                {
                    if (material == null)
                    {
                        missingMaterials++;
                        continue;
                    }

                    materials.Add(material.name);
                    if (material.shader == null)
                    {
                        missingShaders++;
                    }
                }
            }

            foreach (var collider in UnityEngine.Object.FindObjectsByType<Collider>(FindObjectsSortMode.None))
            {
                if (collider is MeshCollider) meshColliders++;
                if (collider is CapsuleCollider) capsuleColliders++;
                if (collider.isTrigger) triggers++;
            }

            var animator = UnityEngine.Object.FindFirstObjectByType<Animator>();
            report.animatorStates = animator != null && animator.runtimeAnimatorController is AnimatorController controller
                ? controller.layers[0].stateMachine.states.Select(s => s.state.name).ToArray()
                : Array.Empty<string>();
            report.missingMaterials = missingMaterials;
            report.missingShaders = missingShaders;
            report.meshColliders = meshColliders;
            report.capsuleColliders = capsuleColliders;
            report.triggerColliders = triggers;
            report.materials = materials.OrderBy(m => m).ToArray();
            report.characterImported = UnityEngine.Object.FindFirstObjectByType<PlayerMovement>() != null;
            report.environmentImported = GameObject.Find("JungleEnvironment") != null;
            report.succeeded = report.renderers > 0 && missingMaterials == 0 && missingShaders == 0 &&
                               report.characterImported && report.environmentImported &&
                               report.collectibles >= 10 && report.checkpoints > 0 &&
                               report.animatorStates.Length >= 4;
            return report;
        }

        private static void EnsureFolder(string path)
        {
            if (AssetDatabase.IsValidFolder(path))
            {
                return;
            }

            string parent = Path.GetDirectoryName(path).Replace("\\", "/");
            string leaf = Path.GetFileName(path);
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
