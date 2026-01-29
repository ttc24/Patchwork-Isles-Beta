import json
import sys
from pathlib import Path

DEFAULT_WORLD_PATH = Path("world/world.json")


def load_world(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def build_graph(world: dict) -> tuple[dict, list[str]]:
    nodes = world.get("nodes", {})
    graph = {node_id: [] for node_id in nodes}
    missing_targets: list[str] = []

    def collect_teleport_targets(effects: object) -> list[str]:
        if not effects:
            return []
        if isinstance(effects, dict):
            effects_list = [effects]
        elif isinstance(effects, list):
            effects_list = effects
        else:
            return []
        targets = []
        for effect in effects_list:
            if not isinstance(effect, dict):
                continue
            if effect.get("type") != "teleport":
                continue
            target = effect.get("target")
            if isinstance(target, str):
                targets.append(target)
        return targets

    for node_id, node in nodes.items():
        for target in collect_teleport_targets(node.get("on_enter")):
            graph[node_id].append(target)
            if target not in nodes:
                missing_targets.append(
                    f"Node {node_id} teleports to missing node {target}"
                )
        for choice in node.get("choices", []) or []:
            target = choice.get("target")
            if isinstance(target, str):
                graph[node_id].append(target)
                if target not in nodes:
                    missing_targets.append(
                        f"Node {node_id} choice targets missing node {target}"
                    )
            for target in collect_teleport_targets(choice.get("effects")):
                graph[node_id].append(target)
                if target not in nodes:
                    missing_targets.append(
                        f"Node {node_id} teleports to missing node {target}"
                    )
    return graph, missing_targets


def traverse_from(start_node: str, graph: dict) -> set:
    if start_node not in graph:
        return set()
    visited = set()
    stack = [start_node]
    while stack:
        current = stack.pop()
        if current in visited:
            continue
        visited.add(current)
        stack.extend(graph.get(current, []))
    return visited


def main() -> None:
    world_path = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_WORLD_PATH
    world = load_world(world_path)
    graph, missing_targets = build_graph(world)
    starts = world.get("starts", [])

    all_reached = set()
    for start in starts:
        node = start.get("node")
        if not isinstance(node, str):
            continue
        reached = traverse_from(node, graph)
        all_reached.update(reached)

    unreachable = sorted(set(graph.keys()) - all_reached)

    print(f"World file: {world_path}")
    print(f"Total nodes: {len(graph)}")
    print(f"Reachable nodes: {len(all_reached)}")
    if unreachable:
        print("Unreachable nodes:")
        for node_id in unreachable:
            print(f"  - {node_id}")
    else:
        print("All nodes reachable from the defined starts.")

    if missing_targets:
        print("Missing targets:")
        for message in missing_targets:
            print(f"  - {message}")
        sys.exit(2)


if __name__ == "__main__":
    main()
