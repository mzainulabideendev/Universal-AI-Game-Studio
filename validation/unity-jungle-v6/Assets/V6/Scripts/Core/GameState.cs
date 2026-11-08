namespace V6
{
    /// <summary>
    /// Explicit gameplay states. Only legal transitions are permitted by
    /// <see cref="GameStateController"/>.
    /// </summary>
    public enum GameState
    {
        Initializing = 0,
        MainMenu = 1,
        Playing = 2,
        Paused = 3,
        GameOver = 4,
        LevelCompleted = 5,
        Restarting = 6,
    }
}
