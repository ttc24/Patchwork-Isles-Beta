#!/usr/bin/env python3
"""Validate the narrative world data for common authoring mistakes."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, Sequence

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_WORLD = REPO_ROOT / "world" / "world.json"

if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from engine.schema import validate_world
from tools.softlock import analyze_softlocks


def load_json(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def parse_args(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate Patchwork Isles world content.")
    parser.add_argument(
        "world_path",
        nargs="?",
        default=str(DEFAULT_WORLD),
        help="Path to the compiled world JSON file.",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str]) -> None:
    args = parse_args(argv[1:])
    world_path = Path(args.world_path).resolve()
    try:
        world = load_json(world_path)
    except json.JSONDecodeError as exc:  # pragma: no cover - defensive error output
        print(f"Failed to parse JSON from {world_path}: {exc}")
        sys.exit(1)

    errors = validate_world(world)
    if errors:
        print("Validation failed (path: message):")
        for err in errors:
            print(f" - {err}")
        sys.exit(1)

    warnings = analyze_softlocks(world)
    if warnings:
        print("Soft-lock warnings (path: message):")
        for warning in warnings:
            print(f" - {warning}")

    print(f"Validation passed for {world_path}.")


if __name__ == "__main__":
    main(sys.argv)
