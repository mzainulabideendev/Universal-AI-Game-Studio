"""Universal AI Game Studio MCP server package.

Every module in this package performs real work: it inspects the filesystem,
runs installed tools, calls documented HTTP APIs or writes verifiable files.
There are no simulated tools. When a dependency is missing the modules return
an explicit ``ok: false`` / ``state: not-configured`` result instead of a fake
success.
"""

SERVER_NAME = "universal-game-studio"
SERVER_VERSION = "1.0.0"
PROTOCOL_VERSION = "2024-11-05"
