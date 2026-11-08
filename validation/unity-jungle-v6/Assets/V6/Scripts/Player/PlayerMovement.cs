using UnityEngine;

namespace V6
{
    /// <summary>
    /// CharacterController-based third-person player movement.
    /// Deliberately uses only CharacterController (no Rigidbody) so collision,
    /// slope handling and ground detection have one owner.
    /// </summary>
    [RequireComponent(typeof(CharacterController))]
    public class PlayerMovement : MonoBehaviour
    {
        [Header("Speeds")]
        [SerializeField] private float walkSpeed = 3.2f;
        [SerializeField] private float runSpeed = 6.4f;
        [SerializeField] private float groundAcceleration = 22f;
        [SerializeField] private float groundDeceleration = 26f;
        [SerializeField] private float airControl = 0.45f;
        [SerializeField] private float turnSpeed = 14f;

        [Header("Jump and gravity")]
        [SerializeField] private float jumpHeight = 1.55f;
        [SerializeField] private float gravity = -24f;
        [SerializeField] private float maxFallSpeed = -45f;
        [SerializeField] private float coyoteTime = 0.12f;
        [SerializeField] private float jumpBufferTime = 0.15f;

        [Header("Safety")]
        [SerializeField] private float fallThresholdY = -8f;
        [SerializeField] private float worldHalfExtent = 62f;

        [Header("References")]
        [SerializeField] private Transform cameraTransform;

        private CharacterController controller;
        private PlayerInputHandler inputHandler;
        private GameStateController states;
        private LevelManager level;
        private GameManager gameManager;
        private readonly GroundDetector groundDetector = new GroundDetector();

        private Vector3 horizontalVelocity;
        private float verticalVelocity;
        private bool jumpConsumed;
        private float coyoteTimer;
        private float jumpBufferTimer;
        private float lastGroundedTime;
        private bool wasGrounded;
        private bool automationMode;
        private Vector3 automationDirection;

        public bool IsGrounded { get; private set; }
        public bool IsFalling => !IsGrounded && verticalVelocity < -0.5f;
        public bool IsJumping { get; private set; }
        public bool JumpedThisFrame { get; private set; }
        public bool LandedThisFrame { get; private set; }
        public bool LeftGroundThisFrame { get; private set; }
        public int JumpCount { get; private set; }
        public float VerticalVelocity => verticalVelocity;
        public float HorizontalSpeed => horizontalVelocity.magnitude;
        public float MoveMagnitude => inputHandler != null ? inputHandler.Move.magnitude : 0f;
        public bool WantsRun => inputHandler != null && inputHandler.Run;
        public Vector3 GroundNormal { get; private set; } = Vector3.up;
        public float GroundSlopeAngle { get; private set; }
        public GroundInfo LastGround { get; private set; }
        public float WalkSpeed => walkSpeed;
        public float RunSpeed => runSpeed;
        public float JumpHeight => jumpHeight;
        public float Gravity => gravity;
        public Transform CameraTransform
        {
            get => cameraTransform;
            set => cameraTransform = value;
        }
        public CharacterController Controller => controller;
        public bool AutomationMode => automationMode;

        private void Awake()
        {
            controller = GetComponent<CharacterController>();
            controller.height = 1.7f;
            controller.radius = 0.32f;
            controller.center = new Vector3(0f, 0.85f, 0f);
            controller.slopeLimit = 46f;
            controller.stepOffset = 0.32f;
            controller.skinWidth = 0.02f;
            controller.minMoveDistance = 0f;
            groundDetector.Mask = ~(1 << gameObject.layer);
            if (!Physics.GetIgnoreLayerCollision(gameObject.layer, 0))
            {
                groundDetector.Mask = ~(1 << gameObject.layer);
            }
        }

        public void Initialize(PlayerInputHandler input, GameStateController stateController,
            LevelManager levelManager, GameManager manager, Transform camera)
        {
            inputHandler = input;
            states = stateController;
            level = levelManager;
            gameManager = manager;
            cameraTransform = camera;
            groundDetector.Mask = ~(1 << gameObject.layer);
            lastGroundedTime = Time.time;
        }

        public void SetAutomationInput(Vector3 worldDirection, bool sprint)
        {
            automationMode = true;
            worldDirection.y = 0f;
            automationDirection = worldDirection.sqrMagnitude > 0.0001f
                ? worldDirection.normalized
                : Vector3.zero;
            if (worldDirection.sqrMagnitude > 0.0001f)
            {
                inputHandler?.SetTestInput(new Vector2(0f, 1f), false, sprint);
            }
            else
            {
                inputHandler?.SetTestInput(Vector2.zero, false, false);
            }
        }

        public void ClearAutomationInput()
        {
            automationMode = false;
            automationDirection = Vector3.zero;
            inputHandler?.ClearTestInput();
        }

        public void SetTestInput(Vector2 move, bool jump, bool sprint = false)
        {
            automationMode = false;
            inputHandler?.SetTestInput(move, jump, sprint);
        }

        public void ClearTestInput()
        {
            automationMode = false;
            inputHandler?.ClearTestInput();
        }

        public void Teleport(Vector3 position, bool resetVelocity = true)
        {
            if (controller == null)
            {
                controller = GetComponent<CharacterController>();
            }

            bool enabledState = controller.enabled;
            controller.enabled = false;
            transform.position = position;
            controller.enabled = enabledState;

            if (resetVelocity)
            {
                ResetVelocity();
            }

            Physics.SyncTransforms();
        }

        public void ResetVelocity()
        {
            horizontalVelocity = Vector3.zero;
            verticalVelocity = -2f;
            IsJumping = false;
            jumpBufferTimer = 0f;
            coyoteTimer = 0f;
            JumpCount = 0;
            wasGrounded = false;
        }

        public void SetFacing(Vector3 worldDirection)
        {
            worldDirection.y = 0f;
            if (worldDirection.sqrMagnitude < 0.0001f)
            {
                return;
            }

            transform.rotation = Quaternion.LookRotation(worldDirection.normalized, Vector3.up);
        }

        private void Update()
        {
            JumpedThisFrame = false;
            LandedThisFrame = false;
            LeftGroundThisFrame = false;

            if (controller == null || inputHandler == null || states == null)
            {
                return;
            }

            LastGround = groundDetector.Detect(controller, controller.slopeLimit);
            IsGrounded = LastGround.IsGrounded;
            GroundNormal = LastGround.Normal;
            GroundSlopeAngle = LastGround.SlopeAngle;

            if (IsGrounded && verticalVelocity <= 0f)
            {
                if (!wasGrounded)
                {
                    LandedThisFrame = verticalVelocity < -2.5f;
                    JumpCount = 0;
                }

                verticalVelocity = -2f;
                IsJumping = false;
                lastGroundedTime = Time.time;
                coyoteTimer = coyoteTime;
            }
            else if (!IsGrounded)
            {
                if (wasGrounded)
                {
                    LeftGroundThisFrame = true;
                }

                coyoteTimer = Mathf.Max(0f, coyoteTimer - Time.deltaTime);
            }

            if (!states.IsGameplayActive)
            {
                inputHandler.ConsumeJump();
                // Still apply gravity so the character settles; never move
                // horizontally or accept input while paused/menu/terminal.
                ApplyGravityOnly();
                wasGrounded = IsGrounded;
                return;
            }

            Vector2 moveInput = automationMode ? Vector2.zero : inputHandler.Move;
            Vector3 desiredDirection = automationMode
                ? automationDirection
                : CameraRelativeDirection(moveInput);
            bool wantsRun = automationMode ? inputHandler.Run : inputHandler.Run;
            float targetSpeed = desiredDirection.sqrMagnitude > 0.0001f
                ? (wantsRun ? runSpeed : walkSpeed)
                : 0f;

            if (IsGrounded && !LastGround.IsWalkableSlope)
            {
                // Steep ground: let the controller slide rather than gaining
                // speed up the slope.
                targetSpeed *= 0.25f;
            }

            Vector3 desiredVelocity = desiredDirection * targetSpeed;
            float acceleration = IsGrounded
                ? (targetSpeed > 0.01f ? groundAcceleration : groundDeceleration)
                : groundAcceleration * Mathf.Clamp01(airControl);
            horizontalVelocity = Vector3.MoveTowards(
                horizontalVelocity, desiredVelocity, acceleration * Time.deltaTime);

            if (desiredDirection.sqrMagnitude > 0.0001f)
            {
                Quaternion targetRotation = Quaternion.LookRotation(desiredDirection, Vector3.up);
                transform.rotation = Quaternion.Slerp(
                    transform.rotation, targetRotation, turnSpeed * Time.deltaTime);
            }

            if (inputHandler.ConsumeJump())
            {
                jumpBufferTimer = jumpBufferTime;
            }
            else
            {
                jumpBufferTimer = Mathf.Max(0f, jumpBufferTimer - Time.deltaTime);
            }

            if (jumpBufferTimer > 0f && (IsGrounded || coyoteTimer > 0f))
            {
                PerformJump();
            }

            verticalVelocity = Mathf.Max(verticalVelocity + gravity * Time.deltaTime, maxFallSpeed);

            Vector3 motion = horizontalVelocity;
            motion.y = verticalVelocity;
            controller.Move(motion * Time.deltaTime);

            if (LandedThisFrame)
            {
                GameplayEventBus.RaisePlayerLanded();
                gameManager?.OnPlayerLanded();
            }

            wasGrounded = IsGrounded;
            CheckSafety();
        }

        private void ApplyGravityOnly()
        {
            verticalVelocity = Mathf.Max(verticalVelocity + gravity * Time.deltaTime, maxFallSpeed);
            controller.Move(new Vector3(0f, verticalVelocity, 0f) * Time.deltaTime);
        }

        private void PerformJump()
        {
            verticalVelocity = ComputeJumpVelocity(jumpHeight, gravity);
            IsGrounded = false;
            IsJumping = true;
            jumpBufferTimer = 0f;
            coyoteTimer = 0f;
            JumpCount++;
            JumpedThisFrame = true;
            GameplayEventBus.RaisePlayerJumped();
        }

        /// <summary>Physics helper kept static so jump maths is unit testable.</summary>
        public static float ComputeJumpVelocity(float height, float gravityValue)
        {
            return Mathf.Sqrt(Mathf.Max(0.01f, height) * -2f * Mathf.Min(-0.01f, gravityValue));
        }

        private Vector3 CameraRelativeDirection(Vector2 move)
        {
            if (move.sqrMagnitude < 0.0001f)
            {
                return Vector3.zero;
            }

            Vector3 forward = cameraTransform != null ? cameraTransform.forward : Vector3.forward;
            Vector3 right = cameraTransform != null ? cameraTransform.right : Vector3.right;
            forward.y = 0f;
            right.y = 0f;
            forward.Normalize();
            right.Normalize();
            Vector3 direction = forward * move.y + right * move.x;
            return direction.sqrMagnitude > 0.0001f ? direction.normalized : Vector3.zero;
        }

        private void CheckSafety()
        {
            if (level == null || gameManager == null || !states.IsGameplayActive)
            {
                return;
            }

            Vector3 position = transform.position;
            bool outside = position.y < fallThresholdY ||
                           Mathf.Abs(position.x) > worldHalfExtent ||
                           Mathf.Abs(position.z) > worldHalfExtent;
            if (outside || level.IsOutsidePlayable(position))
            {
                GameplayEventBus.RaisePlayerFell();
                gameManager.OnPlayerFell();
            }
        }

        private void OnDrawGizmosSelected()
        {
            Gizmos.color = IsGrounded ? Color.green : Color.red;
            Gizmos.DrawWireSphere(transform.position + Vector3.up * 0.1f, 0.32f);
        }
    }
}
