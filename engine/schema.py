"""Shared schema validation utilities for Patchwork Isles."""

from __future__ import annotations

from collections import Counter
from typing import Any, Dict, Iterable, List, Mapping, MutableMapping, Sequence, Tuple


class ValidationContext:
    """Utility container for accumulating validation errors."""

    def __init__(self) -> None:
        self.errors: List[str] = []

    def add(self, message: str) -> None:
        self.errors.append(message)

    def extend(self, messages: Iterable[str]) -> None:
        self.errors.extend(messages)

    def ok(self) -> bool:
        return not self.errors


def require(condition: bool, message: str, ctx: ValidationContext) -> None:
    if not condition:
        ctx.add(message)


def is_non_empty_str(value: Any) -> bool:
    return isinstance(value, str) and value.strip() != ""


def str_or_str_list(value: Any) -> bool:
    if isinstance(value, str):
        return value.strip() != ""
    if isinstance(value, list) and value:
        return all(isinstance(item, str) and item.strip() != "" for item in value)
    return False


def simple_value(value: Any) -> bool:
    return value is None or isinstance(value, (str, int, bool))


def normalize_nodes(raw_nodes: Any) -> Tuple[Dict[str, Dict[str, Any]], List[str]]:
    nodes: Dict[str, Dict[str, Any]] = {}
    ctx = ValidationContext()

    if isinstance(raw_nodes, dict):
        for node_id, payload in raw_nodes.items():
            if not is_non_empty_str(node_id):
                ctx.add("Node identifiers must be non-empty strings.")
                continue
            if not isinstance(payload, dict):
                ctx.add(f"Node '{node_id}' must be an object.")
                continue
            nodes[node_id] = payload
    elif isinstance(raw_nodes, list):
        for idx, entry in enumerate(raw_nodes, start=1):
            if not isinstance(entry, MutableMapping):
                ctx.add(f"Node entry {idx} must be an object.")
                continue
            node_id = entry.get("id")
            if not is_non_empty_str(node_id):
                ctx.add(f"Node entry {idx} is missing a valid 'id'.")
                continue
            payload = dict(entry)
            payload.pop("id", None)
            nodes[node_id] = payload
    else:
        ctx.add("'nodes' must be an object mapping IDs to node definitions or a list of node entries.")

    duplicates = [node_id for node_id, count in Counter(nodes.keys()).items() if count > 1]
    if duplicates:
        dup_list = ", ".join(sorted(set(duplicates)))
        ctx.add(f"Duplicate node IDs found: {dup_list}.")

    return nodes, ctx.errors


def validate_condition(condition: Any, context: str, ctx: ValidationContext) -> None:
    if condition in (None, {}):
        return
    if isinstance(condition, Sequence) and not isinstance(condition, (str, bytes, Mapping)):
        if not condition:
            ctx.add(f"{context}: condition list must not be empty.")
            return
        for idx, sub in enumerate(condition, start=1):
            if not isinstance(sub, Mapping):
                ctx.add(f"{context}: condition list entry {idx} must be an object.")
                continue
            validate_condition(sub, f"{context} (entry {idx})", ctx)
        return
    if not isinstance(condition, Mapping):
        ctx.add(f"{context}: condition must be an object or null.")
        return

    cond_type = condition.get("type")
    if cond_type not in {
        "has_item",
        "missing_item",
        "flag_eq",
        "has_tag",
        "has_advanced_tag",
        "has_trait",
        "rep_at_least",
        "rep_at_least_count",
        "profile_flag_eq",
        "profile_flag_is_true",
        "profile_flag_is_false",
    }:
        ctx.add(f"{context}: unsupported condition type '{cond_type}'.")
        return

    if cond_type in {"has_item", "missing_item"}:
        value = condition.get("value")
        if not is_non_empty_str(value):
            ctx.add(f"{context}: '{cond_type}' requires a non-empty string 'value'.")
    elif cond_type == "flag_eq":
        flag = condition.get("flag")
        value = condition.get("value")
        if not is_non_empty_str(flag):
            ctx.add(f"{context}: 'flag_eq' requires a non-empty string 'flag'.")
        if not simple_value(value):
            ctx.add(f"{context}: 'flag_eq' requires a simple literal 'value'.")
    elif cond_type == "profile_flag_eq":
        flag = condition.get("flag")
        value = condition.get("value")
        if not is_non_empty_str(flag):
            ctx.add(f"{context}: 'profile_flag_eq' requires a non-empty string 'flag'.")
        if not simple_value(value):
            ctx.add(f"{context}: 'profile_flag_eq' requires a simple literal 'value'.")
    elif cond_type in {"profile_flag_is_true", "profile_flag_is_false"}:
        flag = condition.get("flag")
        if not is_non_empty_str(flag):
            ctx.add(f"{context}: '{cond_type}' requires a non-empty string 'flag'.")
    elif cond_type in {"has_tag", "has_trait"}:
        value = condition.get("value")
        if not str_or_str_list(value):
            ctx.add(f"{context}: '{cond_type}' requires a tag or list of tags in 'value'.")
    elif cond_type == "has_advanced_tag":
        value = condition.get("value", [])
        if value not in (None, []):
            if not str_or_str_list(value):
                ctx.add(f"{context}: 'has_advanced_tag' requires tags as a string or list when provided.")
    elif cond_type == "rep_at_least":
        faction = condition.get("faction")
        value = condition.get("value")
        if not is_non_empty_str(faction):
            ctx.add(f"{context}: 'rep_at_least' requires a non-empty string 'faction'.")
        if not isinstance(value, int):
            ctx.add(f"{context}: 'rep_at_least' requires an integer 'value'.")
    elif cond_type == "rep_at_least_count":
        value = condition.get("value")
        count = condition.get("count")
        factions = condition.get("factions")
        if not isinstance(value, int):
            ctx.add(f"{context}: 'rep_at_least_count' requires an integer 'value'.")
        if count is not None and not isinstance(count, int):
            ctx.add(f"{context}: 'rep_at_least_count' optional 'count' must be an integer if provided.")
        if factions is not None and not str_or_str_list(factions):
            ctx.add(f"{context}: 'rep_at_least_count' optional 'factions' must be a string or list of strings.")


def validate_effect(
    effect: Any,
    context: str,
    nodes: Mapping[str, Any],
    endings: Mapping[str, Any],
    ctx: ValidationContext,
) -> None:
    if not isinstance(effect, Mapping):
        ctx.add(f"{context}: effect must be an object.")
        return

    effect_type = effect.get("type")
    if effect_type not in {
        "add_item",
        "remove_item",
        "set_flag",
        "add_tag",
        "add_trait",
        "rep_delta",
        "hp_delta",
        "teleport",
        "end_game",
        "unlock_start",
    }:
        ctx.add(f"{context}: unsupported effect type '{effect_type}'.")
        return

    if effect_type in {"add_item", "remove_item", "add_tag", "add_trait"}:
        value = effect.get("value")
        if not is_non_empty_str(value):
            ctx.add(f"{context}: '{effect_type}' requires a non-empty string 'value'.")
    elif effect_type == "set_flag":
        flag = effect.get("flag")
        value = effect.get("value")
        if not is_non_empty_str(flag):
            ctx.add(f"{context}: 'set_flag' requires a non-empty string 'flag'.")
        if not simple_value(value):
            ctx.add(f"{context}: 'set_flag' requires a simple literal 'value'.")
    elif effect_type == "rep_delta":
        faction = effect.get("faction")
        value = effect.get("value")
        if not is_non_empty_str(faction):
            ctx.add(f"{context}: 'rep_delta' requires a non-empty string 'faction'.")
        if not isinstance(value, int):
            ctx.add(f"{context}: 'rep_delta' requires an integer 'value'.")
    elif effect_type == "hp_delta":
        value = effect.get("value")
        if not isinstance(value, int):
            ctx.add(f"{context}: 'hp_delta' requires an integer 'value'.")
    elif effect_type == "teleport":
        target = effect.get("target")
        if not is_non_empty_str(target):
            ctx.add(f"{context}: 'teleport' requires a non-empty string 'target'.")
        elif target not in nodes and target not in endings:
            ctx.add(f"{context}: teleport target '{target}' does not exist.")
    elif effect_type == "end_game":
        ending = effect.get("ending")
        if not is_non_empty_str(ending):
            ctx.add(f"{context}: 'end_game' requires a non-empty string 'ending'.")
        elif ending not in endings:
            ctx.add(f"{context}: ending '{ending}' is not defined.")
    elif effect_type == "unlock_start":
        value = effect.get("value")
        if not is_non_empty_str(value):
            ctx.add(f"{context}: 'unlock_start' requires a non-empty string 'value'.")


def validate_choice(
    choice: Any,
    node_id: str,
    index: int,
    nodes: Mapping[str, Any],
    endings: Mapping[str, Any],
    ctx: ValidationContext,
) -> None:
    context = f"Choice {index} in node '{node_id}'"
    if not isinstance(choice, Mapping):
        ctx.add(f"{context} must be an object.")
        return

    text = choice.get("text")
    if not is_non_empty_str(text):
        ctx.add(f"{context} requires non-empty 'text'.")

    target = choice.get("target")
    if target is None:
        ctx.add(f"{context} is missing a 'target'.")
    elif not is_non_empty_str(target):
        ctx.add(f"{context} must use a non-empty string 'target'.")
    elif target not in nodes and target not in endings:
        ctx.add(f"{context} targets unknown destination '{target}'.")

    validate_condition(choice.get("condition"), context, ctx)

    effects = choice.get("effects")
    if effects is None:
        return
    if not isinstance(effects, Sequence) or isinstance(effects, (str, bytes)):
        ctx.add(f"{context}: 'effects' must be a list of effect objects if present.")
        return
    for eff_index, effect in enumerate(effects, start=1):
        eff_context = f"{context}, effect {eff_index}"
        validate_effect(effect, eff_context, nodes, endings, ctx)


def validate_world(world: Mapping[str, Any]) -> List[str]:
    ctx = ValidationContext()

    require("nodes" in world, "World data must include a 'nodes' section.", ctx)
    endings = world.get("endings")
    if endings is None:
        endings = {}
    elif not isinstance(endings, Mapping):
        ctx.add("'endings' must be an object mapping ending IDs to descriptions.")
        endings = {}

    nodes, node_errors = normalize_nodes(world.get("nodes"))
    ctx.extend(node_errors)

    # Ensure uniqueness explicitly even if JSON objects already enforce it.
    node_ids = list(nodes.keys())
    duplicates = [node_id for node_id, count in Counter(node_ids).items() if count > 1]
    if duplicates:
        ctx.add(f"Duplicate node IDs detected: {', '.join(sorted(duplicates))}.")

    starts = world.get("starts", [])
    if isinstance(starts, Sequence):
        for idx, start in enumerate(starts, start=1):
            if not isinstance(start, Mapping):
                ctx.add(f"Start entry {idx} must be an object.")
                continue
            node_ref = start.get("node")
            if not is_non_empty_str(node_ref):
                ctx.add(f"Start entry {idx} requires a non-empty 'node'.")
                continue
            if node_ref not in nodes:
                ctx.add(f"Start entry {idx} references unknown node '{node_ref}'.")
    else:
        ctx.add("'starts' must be a list of start definitions if present.")

    for node_id, node in nodes.items():
        if not isinstance(node, Mapping):
            ctx.add(f"Node '{node_id}' must be an object.")
            continue
        on_enter = node.get("on_enter")
        if on_enter is not None:
            if not isinstance(on_enter, Sequence) or isinstance(on_enter, (str, bytes)):
                ctx.add(f"Node '{node_id}' on_enter must be a list of effect objects if present.")
            else:
                for eff_index, effect in enumerate(on_enter, start=1):
                    eff_context = f"Node '{node_id}' on_enter effect {eff_index}"
                    validate_effect(effect, eff_context, nodes, endings, ctx)
        choices = node.get("choices")
        if choices is None:
            continue
        if not isinstance(choices, Sequence):
            ctx.add(f"Node '{node_id}' choices must be provided as a list.")
            continue
        for index, choice in enumerate(choices, start=1):
            validate_choice(choice, node_id, index, nodes, endings, ctx)

    return ctx.errors
