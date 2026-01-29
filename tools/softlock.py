"""Soft-lock analysis helpers for Patchwork Isles validation."""

from __future__ import annotations

from collections import defaultdict, deque
from typing import Any, Dict, Iterable, List, Mapping, Sequence, Tuple

from engine.world_schema import normalize_nodes, path

GATED_CONDITION_TYPES = {
    "flag_eq",
    "has_advanced_tag",
    "has_item",
    "has_tag",
    "has_trait",
    "missing_item",
    "profile_flag_eq",
    "profile_flag_is_false",
    "profile_flag_is_true",
    "rep_at_least",
    "rep_at_least_count",
}


def _is_gated_condition(condition: Any) -> bool:
    if condition in (None, {}, []):
        return False
    if isinstance(condition, Sequence) and not isinstance(condition, (str, bytes, Mapping)):
        return any(_is_gated_condition(entry) for entry in condition)
    if not isinstance(condition, Mapping):
        return True
    cond_type = condition.get("type")
    if not isinstance(cond_type, str):
        return True
    if cond_type in GATED_CONDITION_TYPES:
        return True
    return cond_type.startswith("profile_flag_")


def _iter_choices(nodes: Mapping[str, Any]) -> Iterable[Tuple[str, int, Mapping[str, Any]]]:
    for node_id, node in nodes.items():
        choices = node.get("choices")
        if not isinstance(choices, Sequence) or isinstance(choices, (str, bytes)):
            continue
        for index, choice in enumerate(choices):
            if isinstance(choice, Mapping):
                yield node_id, index, choice


def analyze_softlocks(world: Mapping[str, Any]) -> List[str]:
    nodes, _ = normalize_nodes(world.get("nodes"))
    endings = world.get("endings")
    if not isinstance(endings, Mapping):
        endings = {}

    choice_meta: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    inbound_choices: Dict[str, List[Dict[str, Any]]] = defaultdict(list)

    for node_id, index, choice in _iter_choices(nodes):
        target = choice.get("target")
        gated = _is_gated_condition(choice.get("condition"))
        choice_path = path("nodes", node_id, "choices", index)
        meta = {
            "index": index,
            "target": target,
            "gated": gated,
            "path": choice_path,
        }
        choice_meta[node_id].append(meta)
        if isinstance(target, str):
            inbound_choices[target].append(meta)

    warnings: List[str] = []

    for node_id, choices in choice_meta.items():
        if not choices:
            continue
        ungated = [choice for choice in choices if not choice["gated"]]
        if not ungated:
            choice_paths = ", ".join(choice["path"] for choice in choices)
            warnings.append(
                f"{path('nodes', node_id)}: all choices are gated. Choices: {choice_paths}."
            )

    starts = world.get("starts", [])
    if not isinstance(starts, Sequence) or isinstance(starts, (str, bytes)):
        starts = []

    start_nodes = []
    for start in starts:
        if isinstance(start, Mapping):
            node_ref = start.get("node")
            if isinstance(node_ref, str):
                start_nodes.append(node_ref)

    def traverse(start_node: str, ungated_only: bool) -> Tuple[set[str], List[str]]:
        visited: set[str] = set()
        queue: deque[str] = deque([start_node])
        chain_warnings: List[str] = []
        while queue:
            node_id = queue.popleft()
            if node_id in visited:
                continue
            visited.add(node_id)
            choices = choice_meta.get(node_id, [])
            if ungated_only and choices:
                ungated = [choice for choice in choices if not choice["gated"]]
                if not ungated:
                    choice_paths = ", ".join(choice["path"] for choice in choices)
                    chain_warnings.append(
                        f"{path('nodes', node_id)}: traversal from start '{start_node}'"
                        f" hit node with no ungated exits. Choices: {choice_paths}."
                    )
            for choice in choices:
                if ungated_only and choice["gated"]:
                    continue
                target = choice.get("target")
                if not isinstance(target, str) or target in endings:
                    continue
                if target in nodes:
                    queue.append(target)
        return visited, chain_warnings

    for start_node in start_nodes:
        if start_node not in nodes:
            continue
        reachable_all, _ = traverse(start_node, ungated_only=False)
        reachable_ungated, chain_warnings = traverse(start_node, ungated_only=True)
        warnings.extend(chain_warnings)
        gated_only_nodes = sorted(reachable_all - reachable_ungated)
        for node_id in gated_only_nodes:
            inbound = [choice for choice in inbound_choices.get(node_id, []) if choice["gated"]]
            if inbound:
                choice_paths = ", ".join(choice["path"] for choice in inbound)
            else:
                choice_paths = "(no gated inbound choices recorded)"
            warnings.append(
                f"{path('nodes', node_id)}: reachable from start '{start_node}'"
                f" only via gated choices. Choices: {choice_paths}."
            )

    return warnings
