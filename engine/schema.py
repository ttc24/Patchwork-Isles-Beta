"""Shared schema validation utilities for Patchwork Isles."""

from __future__ import annotations

from collections import Counter
from typing import Any, Iterable, List, Mapping, Sequence

from engine.world_schema import (
    CONDITION_SPECS,
    EFFECT_SPECS,
    format_validation_message,
    is_non_empty_str,
    normalize_nodes,
    path,
)


class ValidationContext:
    """Utility container for accumulating validation errors."""

    def __init__(self) -> None:
        self.errors: List[str] = []

    def add(self, context: str, path_str: str, message: str) -> None:
        self.errors.append(format_validation_message(path_str, context, message))

    def extend(self, messages: Iterable[str]) -> None:
        self.errors.extend(messages)

    def extend_with_path(self, messages: Iterable[str], path_str: str) -> None:
        for message in messages:
            self.errors.append(f"{path_str}: {message}")

    def ok(self) -> bool:
        return not self.errors


def require(condition: bool, context: str, path_str: str, message: str, ctx: ValidationContext) -> None:
    if not condition:
        ctx.add(context, path_str, message)


def validate_condition(
    condition: Any, context: str, path_parts: Sequence[object], ctx: ValidationContext
) -> None:
    if condition in (None, {}):
        return
    if isinstance(condition, Sequence) and not isinstance(condition, (str, bytes, Mapping)):
        if not condition:
            ctx.add(context, path(*path_parts), "condition list must not be empty.")
            return
        for idx, sub in enumerate(condition, start=1):
            if not isinstance(sub, Mapping):
                ctx.add(
                    context,
                    path(*path_parts, idx - 1),
                    f"condition list entry {idx} must be an object.",
                )
                continue
            validate_condition(
                sub,
                f"{context} (entry {idx})",
                (*path_parts, idx - 1),
                ctx,
            )
        return
    if not isinstance(condition, Mapping):
        ctx.add(context, path(*path_parts), "condition must be an object or null.")
        return

    cond_type = condition.get("type")
    spec = CONDITION_SPECS.get(cond_type)
    if spec is None:
        ctx.add(context, path(*path_parts, "type"), f"unsupported condition type '{cond_type}'.")
        return
    ctx.extend_with_path(spec.validate(condition, context), path(*path_parts))


def validate_effect(
    effect: Any,
    context: str,
    nodes: Mapping[str, Any],
    endings: Mapping[str, Any],
    path_parts: Sequence[object],
    ctx: ValidationContext,
) -> None:
    if not isinstance(effect, Mapping):
        ctx.add(context, path(*path_parts), "effect must be an object.")
        return

    effect_type = effect.get("type")
    spec = EFFECT_SPECS.get(effect_type)
    if spec is None:
        ctx.add(context, path(*path_parts, "type"), f"unsupported effect type '{effect_type}'.")
        return
    ctx.extend_with_path(spec.validate(effect, context, nodes, endings), path(*path_parts))


def validate_choice(
    choice: Any,
    node_id: str,
    index: int,
    nodes: Mapping[str, Any],
    endings: Mapping[str, Any],
    path_parts: Sequence[object],
    ctx: ValidationContext,
) -> None:
    context = f"Choice {index} in node '{node_id}'"
    if not isinstance(choice, Mapping):
        ctx.add(context, path(*path_parts), "must be an object.")
        return

    text = choice.get("text")
    if not is_non_empty_str(text):
        ctx.add(context, path(*path_parts, "text"), "requires non-empty 'text'.")

    target = choice.get("target")
    if target is None:
        ctx.add(context, path(*path_parts, "target"), "is missing a 'target'.")
    elif not is_non_empty_str(target):
        ctx.add(context, path(*path_parts, "target"), "must use a non-empty string 'target'.")
    elif target not in nodes and target not in endings:
        ctx.add(
            context,
            path(*path_parts, "target"),
            f"targets unknown destination '{target}'.",
        )

    validate_condition(choice.get("condition"), context, (*path_parts, "condition"), ctx)

    effects = choice.get("effects")
    if effects is None:
        return
    if not isinstance(effects, Sequence) or isinstance(effects, (str, bytes)):
        ctx.add(
            context,
            path(*path_parts, "effects"),
            "'effects' must be a list of effect objects if present.",
        )
        return
    for eff_index, effect in enumerate(effects, start=1):
        eff_context = f"{context}, effect {eff_index}"
        validate_effect(
            effect,
            eff_context,
            nodes,
            endings,
            (*path_parts, "effects", eff_index - 1),
            ctx,
        )


def validate_world(world: Mapping[str, Any]) -> List[str]:
    ctx = ValidationContext()

    require(
        is_non_empty_str(world.get("title")),
        "World data",
        path("title"),
        "must include a non-empty 'title'.",
        ctx,
    )
    require(
        "nodes" in world,
        "World data",
        path("nodes"),
        "must include a 'nodes' section.",
        ctx,
    )
    endings = world.get("endings")
    if endings is None:
        endings = {}
    elif not isinstance(endings, Mapping):
        ctx.add(
            "World data",
            path("endings"),
            "'endings' must be an object mapping ending IDs to descriptions.",
        )
        endings = {}

    nodes, _node_errors = normalize_nodes(world.get("nodes"), ctx)

    # Ensure uniqueness explicitly even if JSON objects already enforce it.
    node_ids = list(nodes.keys())
    duplicates = [node_id for node_id, count in Counter(node_ids).items() if count > 1]
    if duplicates:
        ctx.add(
            "Nodes",
            path("nodes"),
            f"duplicate node IDs detected: {', '.join(sorted(duplicates))}.",
        )

    starts = world.get("starts", [])
    if isinstance(starts, Sequence):
        for idx, start in enumerate(starts, start=1):
            if not isinstance(start, Mapping):
                ctx.add(
                    f"Start entry {idx}",
                    path("starts", idx - 1),
                    "must be an object.",
                )
                continue
            node_ref = start.get("node")
            if not is_non_empty_str(node_ref):
                ctx.add(
                    f"Start entry {idx}",
                    path("starts", idx - 1, "node"),
                    "requires a non-empty 'node'.",
                )
                continue
            if node_ref not in nodes:
                ctx.add(
                    f"Start entry {idx}",
                    path("starts", idx - 1, "node"),
                    f"references unknown node '{node_ref}'.",
                )
    else:
        ctx.add(
            "World data",
            path("starts"),
            "'starts' must be a list of start definitions if present.",
        )

    for node_id, node in nodes.items():
        if not isinstance(node, Mapping):
            ctx.add("Nodes", path("nodes", node_id), f"node '{node_id}' must be an object.")
            continue
        on_enter = node.get("on_enter")
        if on_enter is not None:
            if not isinstance(on_enter, Sequence) or isinstance(on_enter, (str, bytes)):
                ctx.add(
                    f"Node '{node_id}'",
                    path("nodes", node_id, "on_enter"),
                    "on_enter must be a list of effect objects if present.",
                )
            else:
                for eff_index, effect in enumerate(on_enter, start=1):
                    eff_context = f"Node '{node_id}' on_enter effect {eff_index}"
                    validate_effect(
                        effect,
                        eff_context,
                        nodes,
                        endings,
                        ("nodes", node_id, "on_enter", eff_index - 1),
                        ctx,
                    )
        choices = node.get("choices")
        if choices is None:
            continue
        if not isinstance(choices, Sequence):
            ctx.add(
                f"Node '{node_id}'",
                path("nodes", node_id, "choices"),
                "choices must be provided as a list.",
            )
            continue
        for index, choice in enumerate(choices, start=1):
            validate_choice(
                choice,
                node_id,
                index,
                nodes,
                endings,
                ("nodes", node_id, "choices", index - 1),
                ctx,
            )

    return ctx.errors
