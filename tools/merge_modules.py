#!/usr/bin/env python3
"""Combine module JSON files into a single world file."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, Mapping

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_WORLD_PATH = REPO_ROOT / "world" / "world.json"
DEFAULT_MODULES_DIR = REPO_ROOT / "world" / "modules"


def load_json(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def ensure_world_structure(world: Dict[str, Any]) -> Dict[str, Any]:
    nodes = world.get("nodes")
    if nodes is None:
        nodes = {}
    if not isinstance(nodes, dict):
        raise ValueError("Base world must store nodes as an object mapping IDs to node definitions.")

    starts = world.get("starts")
    if starts is None:
        starts = []
    if not isinstance(starts, list):
        raise ValueError("Base world must use a list for starts.")

    endings = world.get("endings")
    if endings is None:
        endings = {}
    if not isinstance(endings, dict):
        raise ValueError("Base world must use an object for endings.")

    factions = world.get("factions")
    if factions is None:
        factions = []
    if not isinstance(factions, list):
        raise ValueError("Base world must use a list for factions.")

    world["nodes"] = nodes
    world["starts"] = starts
    world["endings"] = endings
    world["factions"] = factions
    return world


def extract_nodes(module: Mapping[str, Any], module_name: str, errors: list[str]) -> Dict[str, Any]:
    raw_nodes = module.get("nodes")
    if raw_nodes is None:
        return {}

    entries: list[tuple[str, Any]] = []
    if isinstance(raw_nodes, dict):
        entries = list(raw_nodes.items())
    elif isinstance(raw_nodes, list):
        for idx, entry in enumerate(raw_nodes, start=1):
            if not isinstance(entry, Mapping):
                errors.append(f"{module_name}: node entry {idx} must be an object.")
                continue
            node_id = entry.get("id")
            if not isinstance(node_id, str) or not node_id.strip():
                errors.append(f"{module_name}: node entry {idx} is missing an 'id'.")
                continue
            payload = dict(entry)
            payload.pop("id", None)
            entries.append((node_id, payload))
    else:
        errors.append(f"{module_name}: 'nodes' must be an object or a list of node entries.")
        return {}

    nodes: Dict[str, Any] = {}
    for node_id, payload in entries:
        if not isinstance(node_id, str) or not node_id.strip():
            errors.append(f"{module_name}: node id '{node_id}' must be a non-empty string.")
            continue
        if not isinstance(payload, Mapping):
            errors.append(f"{module_name}: node '{node_id}' must be an object definition.")
            continue
        if node_id in nodes:
            errors.append(f"{module_name}: node '{node_id}' defined multiple times.")
            continue
        nodes[node_id] = dict(payload)

    return nodes


def merge_world(base_world: Dict[str, Any], modules_dir: Path) -> tuple[Dict[str, Any], list[Path]]:
    base = ensure_world_structure(base_world)
    errors: list[str] = []
    module_files = sorted(p for p in modules_dir.glob("*.json") if p.is_file())

    for module_path in module_files:
        data = load_json(module_path)
        module_name = module_path.name

        module_nodes = extract_nodes(data, module_name, errors)
        for node_id, node_payload in module_nodes.items():
            if node_id in base["nodes"]:
                errors.append(f"{module_name}: node '{node_id}' already exists in base world.")
            else:
                base["nodes"][node_id] = node_payload

        module_endings = data.get("endings")
        if module_endings is not None:
            if not isinstance(module_endings, Mapping):
                errors.append(f"{module_name}: 'endings' must be an object.")
            else:
                for ending_id, ending_text in module_endings.items():
                    if ending_id in base["endings"] and base["endings"][ending_id] != ending_text:
                        errors.append(
                            f"{module_name}: ending '{ending_id}' conflicts with existing definition."
                        )
                    else:
                        base["endings"].setdefault(ending_id, ending_text)

        module_starts = data.get("starts")
        if module_starts is not None:
            if not isinstance(module_starts, list):
                errors.append(f"{module_name}: 'starts' must be a list.")
            else:
                base["starts"].extend(module_starts)

        module_factions = data.get("factions")
        if module_factions is not None:
            if not isinstance(module_factions, list):
                errors.append(f"{module_name}: 'factions' must be a list.")
            else:
                for faction in module_factions:
                    if isinstance(faction, str) and faction not in base["factions"]:
                        base["factions"].append(faction)

    if errors:
        print("Merge aborted due to errors:")
        for err in errors:
            print(f" - {err}")
        sys.exit(1)

    return base, module_files


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Merge world modules into a single world file.")
    parser.add_argument(
        "--world",
        type=Path,
        default=DEFAULT_WORLD_PATH,
        help="Path to the existing compiled world JSON file (created if missing).",
    )
    parser.add_argument(
        "--modules",
        type=Path,
        default=DEFAULT_MODULES_DIR,
        help="Directory containing module JSON files.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="Optional path for the merged output. Defaults to --world path.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    world_path: Path = args.world.resolve()
    modules_dir: Path = args.modules.resolve()
    output_path: Path = args.output.resolve() if args.output else world_path

    if not modules_dir.exists():
        print(f"Module directory {modules_dir} does not exist.")
        sys.exit(1)

    base_world: Dict[str, Any]
    if world_path.exists():
        base_world = load_json(world_path)
    else:
        base_world = {
            "title": "",
            "factions": [],
            "starts": [],
            "endings": {},
            "nodes": {},
        }

    merged, module_files = merge_world(base_world, modules_dir)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as handle:
        json.dump(merged, handle, indent=4, ensure_ascii=False)
        handle.write("\n")

    print(f"Merged {len(module_files)} module(s) into {output_path}.")


if __name__ == "__main__":
    main()
