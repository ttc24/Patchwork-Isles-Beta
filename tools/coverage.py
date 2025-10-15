import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Dict, Iterable, List

DEFAULT_WORLD_PATH = Path("world/world.json")

CORE_TAGS = [
    "Emissary",
    "Trickster",
    "Arbiter",
    "Sneaky",
    "Scout",
    "Tinkerer",
    "Archivist",
    "Cartographer",
    "Healer",
    "Weaver",
    "Lumenar",
    "Resonant",
]


def load_world(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def infer_hub(node_id: str) -> str:
    if node_id.startswith("ending_"):
        return "endings"
    parts = node_id.split("_")
    if len(parts) == 1:
        return node_id
    return parts[0]


def iter_has_tag_conditions(payload: Any) -> Iterable[Dict[str, Any]]:
    if isinstance(payload, dict):
        if payload.get("type") == "has_tag":
            yield payload
        for value in payload.values():
            yield from iter_has_tag_conditions(value)
    elif isinstance(payload, list):
        for entry in payload:
            yield from iter_has_tag_conditions(entry)


def extract_tags(condition: Dict[str, Any]) -> List[str]:
    value = condition.get("value")
    if value is None:
        return []
    if isinstance(value, list):
        return [tag for tag in value if isinstance(tag, str)]
    if isinstance(value, str):
        return [value]
    return []


def audit(world: Dict[str, Any]) -> int:
    global_counts: Counter[str] = Counter()
    hub_counts: defaultdict[str, Counter[str]] = defaultdict(Counter)

    for node_id, node in world.get("nodes", {}).items():
        hub_id = infer_hub(node_id)
        for choice in node.get("choices", []) or []:
            for condition in iter_has_tag_conditions(choice.get("condition")):
                for tag in extract_tags(condition):
                    global_counts[tag] += 1
                    hub_counts[hub_id][tag] += 1

    print("Per-hub tag coverage:")
    for hub_id in sorted(hub_counts):
        print(f"  {hub_id}:")
        for tag, count in hub_counts[hub_id].most_common():
            print(f"    {tag}: {count}")
    print()

    print("Global tag coverage:")
    for tag, count in global_counts.most_common():
        print(f"  {tag}: {count}")
    print()

    exit_code = 0

    print("Balance checks:")

    missing_core = [tag for tag in CORE_TAGS if global_counts[tag] < 10]
    if missing_core:
        exit_code = 1
        print("  [FAIL] Core tags below 10 uses:")
        for tag in missing_core:
            print(f"    - {tag}: {global_counts[tag]}")
    else:
        print("  [OK] All core tags appear at least 10 times.")

    advanced_tags = sorted(tag for tag in global_counts if tag not in CORE_TAGS)
    missing_adv = [tag for tag in advanced_tags if global_counts[tag] < 4]
    if missing_adv:
        exit_code = 1
        print("  [FAIL] Advanced tags below 4 uses:")
        for tag in missing_adv:
            print(f"    - {tag}: {global_counts[tag]}")
    else:
        print("  [OK] All advanced tags appear at least 4 times.")

    undercovered = defaultdict(list)
    for tag in CORE_TAGS:
        if global_counts[tag] < 8:
            for hub_id, counts in hub_counts.items():
                if counts[tag]:
                    undercovered[hub_id].append(tag)

    if undercovered:
        print("  [WARN] Hubs relying on under-covered core tags (<8 global uses):")
        for hub_id in sorted(undercovered):
            tags = ", ".join(sorted(undercovered[hub_id]))
            print(f"    - {hub_id}: {tags}")
    else:
        print("  [OK] No hubs rely on core tags with fewer than 8 global uses.")

    return exit_code


def main() -> None:
    parser = argparse.ArgumentParser(description="Audit tag coverage across hubs.")
    parser.add_argument("world", nargs="?", default=str(DEFAULT_WORLD_PATH), help="Path to world JSON file")
    args = parser.parse_args()

    world_path = Path(args.world)
    world = load_world(world_path)
    exit_code = audit(world)
    raise SystemExit(exit_code)


if __name__ == "__main__":
    main()
