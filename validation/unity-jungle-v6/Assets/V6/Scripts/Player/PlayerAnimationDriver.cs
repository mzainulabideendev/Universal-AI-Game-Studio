using UnityEngine;

namespace V6
{
    /// <summary>
    /// Maps gameplay movement to Animator parameters. Root motion is disabled
    /// on the Animator, so animation can never drive the CharacterController.
    /// </summary>
    public class PlayerAnimationDriver : MonoBehaviour
    {
        [SerializeField] private Animator animator;
        [SerializeField] private PlayerMovement movement;
        [SerializeField] private GameStateController states;

        [SerializeField] private float idleThreshold = 0.06f;
        [SerializeField] private float runThreshold = 0.62f;

        public Animator Animator => animator;
        public string CurrentLocomotion { get; private set; } = "Idle";
        public float LastSpeedParameter { get; private set; }
        public bool LastGroundedParameter { get; private set; }

        public void Initialize(PlayerMovement playerMovement, GameStateController stateController)
        {
            movement = playerMovement;
            states = stateController;
            if (animator == null)
            {
                animator = GetComponent<Animator>();
            }

            if (animator == null && playerMovement != null)
            {
                animator = playerMovement.GetComponentInChildren<Animator>();
            }

            if (animator != null)
            {
                animator.applyRootMotion = false;
                animator.cullingMode = AnimatorCullingMode.AlwaysAnimate;
            }
        }

        public void Initialize(Animator targetAnimator, PlayerMovement playerMovement, GameStateController stateController)
        {
            animator = targetAnimator;
            movement = playerMovement;
            states = stateController;
            if (animator != null)
            {
                animator.applyRootMotion = false;
                animator.cullingMode = AnimatorCullingMode.AlwaysAnimate;
            }
        }

        private void LateUpdate()
        {
            if (animator == null || movement == null)
            {
                return;
            }

            bool active = states == null || states.IsGameplayActive;
            float speed = active && movement.HorizontalSpeed > idleThreshold
                ? Mathf.Clamp01(movement.HorizontalSpeed / Mathf.Max(0.1f, movement.RunSpeed))
                : 0f;

            // Preserve a readable walk/run split for the blend thresholds.
            speed = Mathf.Clamp(speed, 0f, 1f);
            LastSpeedParameter = speed;
            LastGroundedParameter = movement.IsGrounded;

            if (animator != null)
            {
                float targetSpeed = speed;
                animator.SetFloat("Speed", targetSpeed, 0.08f, Time.deltaTime);
                animator.SetBool("Grounded", movement.IsGrounded);
                animator.SetFloat("VerticalSpeed", movement.VerticalVelocity);

                if (movement.JumpedThisFrame)
                {
                    animator.SetTrigger("Jump");
                }
            }

            if (!movement.IsGrounded)
            {
                CurrentLocomotion = movement.VerticalVelocity > 0.1f ? "Jump" : "Fall";
            }
            else if (speed > runThreshold)
            {
                CurrentLocomotion = "Run";
            }
            else if (speed > idleThreshold)
            {
                CurrentLocomotion = "Walk";
            }
            else
            {
                CurrentLocomotion = "Idle";
            }
        }
    }
}
