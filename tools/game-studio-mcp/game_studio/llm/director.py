"""AI Game Director entry point.

Kept as a separate module so the director behaviour can evolve without changing
the reasoning primitives. All execution remains in governed MCP tools.
"""

from __future__ import annotations

from .reasoning import game_director_plan

__all__ = ["game_director_plan"]
