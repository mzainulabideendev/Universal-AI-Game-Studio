using UnityEngine;

namespace V6
{
    /// <summary>
    /// Single input entry point. Reads the project's configured legacy Input
    /// Manager (the Input System package is not installed in this offline
    /// project) and exposes buffered, edge-triggered actions. Tests and the
    /// automated demo inject input through <see cref="SetTestInput"/>.
    /// </summary>
    public class PlayerInputHandler : MonoBehaviour
    {
        [Header("Bindings (legacy Input Manager axes)")]
        [SerializeField] private string horizontalAxis = "Horizontal";
        [SerializeField] private string verticalAxis = "Vertical";
        [SerializeField] private string jumpButton = "Jump";
        [SerializeField] private string mouseXAxis = "Mouse X";
        [SerializeField] private string mouseYAxis = "Mouse Y";

        [Header("Behaviour")]
        [SerializeField] private float jumpBufferSeconds = 0.15f;
        [SerializeField] private float lookSensitivity = 2.2f;
        [SerializeField] private bool enableMouseLook = true;

        private float jumpBufferTimer;
        private bool testMode;
        private Vector2 testMove;
        private bool testRun;
        private bool testJumpQueued;

        public Vector2 Move { get; private set; }
        public bool Run { get; private set; }
        public Vector2 MouseDelta { get; private set; }
        public bool PausePressed { get; private set; }
        public bool RestartPressed { get; private set; }
        public bool StartPressed { get; private set; }
        public bool LookEnabled { get; set; } = true;
        public bool InputEnabled { get; set; } = true;
        public float LookSensitivity
        {
            get => lookSensitivity;
            set => lookSensitivity = Mathf.Clamp(value, 0.2f, 5f);
        }

        public bool MouseLookEnabled
        {
            get => enableMouseLook;
            set => enableMouseLook = value;
        }

        public void SetTestInput(Vector2 move, bool jump, bool sprint = false)
        {
            testMode = true;
            testMove = Vector2.ClampMagnitude(move, 1f);
            testRun = sprint;
            if (jump)
            {
                testJumpQueued = true;
            }
        }

        public void ClearTestInput()
        {
            testMode = false;
            testMove = Vector2.zero;
            testRun = false;
            testJumpQueued = false;
            jumpBufferTimer = 0f;
        }

        /// <summary>Consumes a buffered jump request. Returns true once per press.</summary>
        public bool ConsumeJump()
        {
            if (jumpBufferTimer <= 0f)
            {
                return false;
            }

            jumpBufferTimer = 0f;
            return true;
        }

        public void QueueJump()
        {
            jumpBufferTimer = jumpBufferSeconds;
        }

        private void Update()
        {
            PausePressed = false;
            RestartPressed = false;
            StartPressed = false;
            MouseDelta = Vector2.zero;

            if (!InputEnabled)
            {
                Move = Vector2.zero;
                Run = false;
                jumpBufferTimer = 0f;
                return;
            }

            PausePressed = Input.GetKeyDown(KeyCode.Escape);
            RestartPressed = Input.GetKeyDown(KeyCode.R);
            StartPressed = Input.GetKeyDown(KeyCode.Return) ||
                           Input.GetKeyDown(KeyCode.KeypadEnter) ||
                           Input.GetKeyDown(KeyCode.Space);

            if (testMode)
            {
                Move = testMove;
                Run = testRun;
                if (testJumpQueued)
                {
                    jumpBufferTimer = jumpBufferSeconds;
                    testJumpQueued = false;
                }
            }
            else
            {
                Move = Vector2.ClampMagnitude(new Vector2(
                    SafeAxis(horizontalAxis), SafeAxis(verticalAxis)), 1f);
                Run = Input.GetKey(KeyCode.LeftShift) || Input.GetKey(KeyCode.RightShift);
                bool jumpDown = Input.GetButtonDown(jumpButton) ||
                                Input.GetKeyDown(KeyCode.Space);
                if (jumpDown)
                {
                    jumpBufferTimer = jumpBufferSeconds;
                }

                if (enableMouseLook && LookEnabled)
                {
                    MouseDelta = new Vector2(SafeAxis(mouseXAxis), SafeAxis(mouseYAxis));
                }
            }

            jumpBufferTimer = Mathf.Max(0f, jumpBufferTimer - Time.unscaledDeltaTime);
        }

        private static float SafeAxis(string axis)
        {
            try
            {
                return Input.GetAxisRaw(axis);
            }
            catch (System.ArgumentException)
            {
                // Axis absent from a trimmed InputManager: behave as neutral
                // instead of throwing every frame.
                return 0f;
            }
        }
    }
}
