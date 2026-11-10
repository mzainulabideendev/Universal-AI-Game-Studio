#!/usr/bin/env python3
"""V6 Phase 6 demo: free-provider policy, routing, design and asset research.

Deterministic only. No provider, network, credential, asset download, install or
engine operation is used. Run from the repository root:

    python scripts/v6-phase6-demo.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools" / "game-studio-mcp"))

from game_studio.llm import (  # noqa: E402
    asset_research, free_policy, free_routing, intelligence, quota,
)


def main() -> int:
    catalog = free_policy.catalog()
    print("== Free provider catalog ==")
    for provider in catalog["providers"]:
        print(f"- {provider['provider']:10s} status={provider['status']:12s} "
              f"free={provider['free']} docs={provider['verified_on']}")

    route = free_routing.route("game_design_reasoning")
    print("\n== Free-only route ==")
    print(f"mode={route['mode']} selected={route['selected']} "
          f"paid_fallback={route['fallback_plan']['paid_switch']}")

    game = "Create a 3D jungle adventure where a monkey collects bananas."
    design = intelligence.design(game)
    print("\n== Game design proposal ==")
    print(f"concept={design['concept']}")
    print(f"requirements={design['requirements_summary']} "
          f"schema_valid={design['validation']['valid']} executable={design['executable']}")
    print("coverage=" + ", ".join(item["id"] for item in design["coverage"]))

    character = intelligence.character_spec_from_design(design)
    environment = intelligence.environment_spec_from_design(design)
    print(f"character_spec_valid={character['validation']['valid']} "
          f"ai_generated={character['ai_generated_asset']}")
    print(f"environment_spec_valid={environment['validation']['valid']} "
          f"ai_generated={environment['ai_generated_asset']}")

    research = asset_research.capabilities()
    print("\n== Asset-generation research ==")
    print(f"free_hosted_available_now={research['verified_free_hosted_available_now']}")
    print(f"asset_generation_performed={research['asset_generation_performed']} "
          f"procedural_blender_is_not_ai={research['procedural_blender_is_not_ai']}")

    ledger = quota.status()
    print("\n== Free-quota ledger ==")
    print(json.dumps({"day": ledger["day"], "totals": ledger["totals"],
                      "policy": ledger["policy"]}, indent=2))
    print("\nNo provider was contacted and no asset was generated.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
