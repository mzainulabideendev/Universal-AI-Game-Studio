using UnityEngine;

namespace V5
{
    public class GameManager : MonoBehaviour
    {
        public static GameManager Instance { get; private set; }

        public Transform Player;
        public HUDController Hud;
        public BananaCollectible[] Bananas;
        public int TotalBananas;
        public Vector3 PlayerStart;

        public int Score { get; private set; }

        private void Awake()
        {
            Instance = this;
            if (TotalBananas <= 0 && Bananas != null)
            {
                TotalBananas = Bananas.Length;
            }
            PlayerStart = Player != null ? Player.position : Vector3.zero;
        }

        private void Start()
        {
            RefreshHud();
        }

        private void Update()
        {
            if (Input.GetKeyDown(KeyCode.R))
            {
                ResetState();
            }
        }

        public void AddBanana()
        {
            Score += 1;
            RefreshHud();
            if (Hud != null && Score >= TotalBananas)
            {
                Hud.ShowComplete(true);
            }
        }

        public void ResetState()
        {
            Score = 0;
            Time.timeScale = 1f;
            if (Player != null)
            {
                var controller = Player.GetComponent<MonkeyController>();
                if (controller != null)
                {
                    controller.Teleport(PlayerStart);
                }
                else
                {
                    Player.position = PlayerStart;
                }
            }
            if (Bananas != null)
            {
                foreach (var banana in Bananas)
                {
                    if (banana != null)
                    {
                        banana.ResetBanana();
                    }
                }
            }
            if (Hud != null)
            {
                Hud.ShowComplete(false);
            }
            RefreshHud();
        }

        private void RefreshHud()
        {
            if (Hud != null)
            {
                Hud.SetScore(Score, TotalBananas);
            }
        }
    }
}
