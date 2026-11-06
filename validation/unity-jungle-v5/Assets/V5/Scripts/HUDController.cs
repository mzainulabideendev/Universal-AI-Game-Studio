using UnityEngine;
using UnityEngine.UI;

namespace V5
{
    public class HUDController : MonoBehaviour
    {
        public Text scoreText;
        public Text messageText;
        public Text helpText;

        public void SetScore(int score, int total)
        {
            if (scoreText != null)
            {
                scoreText.text = $"Bananas: {score} / {total}";
            }
        }

        public void ShowComplete(bool visible)
        {
            if (messageText != null)
            {
                messageText.text = "All bananas collected! Press R to play again.";
                messageText.gameObject.SetActive(visible);
            }
        }
    }
}
