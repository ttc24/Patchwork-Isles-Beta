"""Shared schema validation utilities for Patchwork Isles."""

from __future__ import annotations

from collections import Counter
from typing import Any, Iterable, List, Mapping, Sequence

from engine.world_schema import (
    CONDITION_SPECS,
    EFFECT_SPECS,
    is_non_empty_str,
    normalize_nodes,
)


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
    spec = CONDITION_SPECS.get(cond_type)
    if spec is None:
        ctx.add(f"{context}: unsupported condition type '{cond_type}'.")
        return
    ctx.extend(spec.validate(condition, context))


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
    spec = EFFECT_SPECS.get(effect_type)
    if spec is None:
        ctx.add(f"{context}: unsupported effect type '{effect_type}'.")
        return
    ctx.extend(spec.validate(effect, context, nodes, endings))


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

    require(is_non_empty_str(world.get("title")), "World data must include a non-empty 'title'.", ctx)
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
