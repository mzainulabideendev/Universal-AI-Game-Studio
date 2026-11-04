"""Provider-independent LLM reasoning layer.

The LLM understands, reasons and drafts plans. It never executes tools,
commands, downloads or file edits. Every action still goes through the
governed MCP tools. See ``game_studio/llm/client.py`` for the boundary.
"""

from .config import load_config, status, redact
from .client import LLMClient, LLMError
from . import director, reasoning, schemas

__all__ = ["load_config", "status", "redact", "LLMClient", "LLMError",
           "reasoning", "schemas", "director"]
