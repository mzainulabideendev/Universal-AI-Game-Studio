using UnityEngine;

namespace V5
{
    [RequireComponent(typeof(CharacterController))]
    public class MonkeyController : MonoBehaviour
    {
        public float walkSpeed = 3.6f;
        public float runSpeed = 7.2f;
        public float jumpHeight = 1.7f;
        public float gravity = -22f;
        public float turnSpeed = 12f;
        public Transform cameraTransform;

        private CharacterController controller;
        private Animator animator;
        private Vector2 input;
        private bool run;
        private bool jumpRequested;
        private bool testMode;
        private float verticalVelocity;

        public Vector3 StartPosition { get; private set; }
        public bool IsGrounded { get; private set; }
        public float VerticalVelocity => verticalVelocity;
        public Animator Animator => animator;
        public CharacterController Controller => controller;

        private void Awake()
        {
            controller = GetComponent<CharacterController>();
            animator = GetComponentInChildren<Animator>();
            StartPosition = transform.position;
        }

        public void SetCamera(Transform target)
        {
            cameraTransform = target;
        }

        public void SetTestInput(Vector2 move, bool jump, bool sprint = false)
        {
            testMode = true;
            input = Vector2.ClampMagnitude(move, 1f);
            run = sprint;
            if (jump)
            {
                jumpRequested = true;
            }
        }

        public void ClearTestInput()
        {
            testMode = false;
            input = Vector2.zero;
            run = false;
        }

        public void Teleport(Vector3 position)
        {
            controller.enabled = false;
            transform.position = position;
            controller.enabled = true;
            verticalVelocity = 0f;
        }

        private void Update()
        {
            if (!testMode)
            {
                input = new Vector2(Input.GetAxisRaw("Horizontal"), Input.GetAxisRaw("Vertical"));
                run = Input.GetKey(KeyCode.LeftShift) || Input.GetKey(KeyCode.RightShift);
                if (Input.GetButtonDown("Jump") || Input.GetKeyDown(KeyCode.Space))
                {
                    jumpRequested = true;
                }
            }

            input = Vector2.ClampMagnitude(input, 1f);
            Vector3 forward = cameraTransform != null ? cameraTransform.forward : Vector3.forward;
            Vector3 right = cameraTransform != null ? cameraTransform.right : Vector3.right;
            forward.y = 0f;
            right.y = 0f;
            forward.Normalize();
            right.Normalize();
            Vector3 move = forward * input.y + right * input.x;

            IsGrounded = controller.isGrounded ||
                         Physics.Raycast(transform.position + Vector3.up * 0.15f, Vector3.down,
                             0.35f, ~0, QueryTriggerInteraction.Ignore);

            if (move.sqrMagnitude > 0.001f)
            {
                Quaternion target = Quaternion.LookRotation(move, Vector3.up);
                transform.rotation = Quaternion.Slerp(transform.rotation, target,
                    turnSpeed * Time.deltaTime);
            }

            if (IsGrounded && verticalVelocity < 0f)
            {
                verticalVelocity = -2f;
            }

            if (jumpRequested && IsGrounded)
            {
                verticalVelocity = Mathf.Sqrt(jumpHeight * -2f * gravity);
                if (animator != null)
                {
                    animator.SetTrigger("Jump");
                }
            }
            jumpRequested = false;

            verticalVelocity += gravity * Time.deltaTime;
            Vector3 velocity = move * (run ? runSpeed : walkSpeed);
            velocity.y = verticalVelocity;
            controller.Move(velocity * Time.deltaTime);

            if (animator != null)
            {
                float targetSpeed = move.magnitude * (run ? 1f : 0.55f);
                animator.SetFloat("Speed", targetSpeed, 0.08f, Time.deltaTime);
                animator.SetBool("Grounded", IsGrounded);
            }
        }
    }
}
