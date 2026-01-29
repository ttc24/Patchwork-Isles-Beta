"""Machine-readable schema specs for Patchwork Isles worlds."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
import json
from typing import Any, Callable, Dict, List, Mapping, MutableMapping, Sequence, Tuple

ConditionValidator = Callable[[Mapping[str, Any], str], List[str]]
EffectValidator = Callable[[Mapping[str, Any], str, Mapping[str, Any], Mapping[str, Any]], List[str]]


def path(*parts: object) -> str:
    path_str = ""
    for part in parts:
        if isinstance(part, int):
            path_str = f"{path_str}[{part}]"
            continue
        if not isinstance(part, str):
            part = str(part)
        if part.isidentifier():
            path_str = f"{path_str}.{part}" if path_str else part
        else:
            path_str = f'{path_str}[{json.dumps(part)}]'
    return path_str


def format_validation_message(path_str: str, context: str, message: str) -> str:
    if context:
        return f"{path_str}: {context}: {message}"
    return f"{path_str}: {message}"


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


def normalize_nodes(
    raw_nodes: Any, ctx: Any | None = None
) -> Tuple[Dict[str, Dict[str, Any]], List[str]]:
    nodes: Dict[str, Dict[str, Any]] = {}
    errors: List[str] = []
    node_ids: List[str] = []

    def add_error(context: str, path_parts: Sequence[object], message: str) -> None:
        path_str = path(*path_parts)
        errors.append(format_validation_message(path_str, context, message))
        if ctx is not None:
            ctx.add(context, path_str, message)

    if isinstance(raw_nodes, dict):
        for node_id, payload in raw_nodes.items():
            if not is_non_empty_str(node_id):
                add_error("Nodes", ("nodes",), "node identifiers must be non-empty strings.")
                continue
            if not isinstance(payload, dict):
                add_error(
                    "Nodes",
                    ("nodes", node_id),
                    f"node '{node_id}' must be an object.",
                )
                continue
            nodes[node_id] = payload
        node_ids = list(nodes.keys())
    elif isinstance(raw_nodes, list):
        for idx, entry in enumerate(raw_nodes, start=1):
            if not isinstance(entry, MutableMapping):
                add_error(
                    f"Node entry {idx}",
                    ("nodes", idx - 1),
                    "must be an object.",
                )
                continue
            node_id = entry.get("id")
            if not is_non_empty_str(node_id):
                add_error(
                    f"Node entry {idx}",
                    ("nodes", idx - 1, "id"),
                    "is missing a valid 'id'.",
                )
                continue
            node_ids.append(node_id)
            payload = dict(entry)
            payload.pop("id", None)
            nodes[node_id] = payload
    else:
        add_error(
            "World data",
            ("nodes",),
            "must be an object mapping IDs to node definitions or a list of node entries.",
        )

    duplicates = [node_id for node_id, count in Counter(node_ids).items() if count > 1]
    if duplicates:
        dup_list = ", ".join(sorted(set(duplicates)))
        add_error("Nodes", ("nodes",), f"duplicate node IDs found: {dup_list}.")

    return nodes, errors


@dataclass(frozen=True)
class ConditionSpec:
    required_fields: Tuple[str, ...]
    optional_fields: Tuple[str, ...]
    field_rules: Mapping[str, str]
    validate: ConditionValidator


@dataclass(frozen=True)
class EffectSpec:
    required_fields: Tuple[str, ...]
    optional_fields: Tuple[str, ...]
    field_rules: Mapping[str, str]
    validate: EffectValidator


def _validate_flag_eq(condition: Mapping[str, Any], context: str) -> List[str]:
    errors: List[str] = []
    flag = condition.get("flag")
    value = condition.get("value")
    if not is_non_empty_str(flag):
        errors.append(f"{context}: 'flag_eq' requires a non-empty string 'flag'.")
    if not simple_value(value):
        errors.append(f"{context}: 'flag_eq' requires a simple literal 'value'.")
    return errors


def _validate_profile_flag_eq(condition: Mapping[str, Any], context: str) -> List[str]:
    errors: List[str] = []
    flag = condition.get("flag")
    value = condition.get("value")
    if not is_non_empty_str(flag):
        errors.append(f"{context}: 'profile_flag_eq' requires a non-empty string 'flag'.")
    if not simple_value(value):
        errors.append(f"{context}: 'profile_flag_eq' requires a simple literal 'value'.")
    return errors


def _validate_profile_flag_bool(condition: Mapping[str, Any], context: str, name: str) -> List[str]:
    errors: List[str] = []
    flag = condition.get("flag")
    if not is_non_empty_str(flag):
        errors.append(f"{context}: '{name}' requires a non-empty string 'flag'.")
    return errors


def _validate_has_tag(condition: Mapping[str, Any], context: str, name: str) -> List[str]:
    errors: List[str] = []
    value = condition.get("value")
    if not str_or_str_list(value):
        errors.append(f"{context}: '{name}' requires a tag or list of tags in 'value'.")
    return errors


def _validate_has_advanced_tag(condition: Mapping[str, Any], context: str) -> List[str]:
    errors: List[str] = []
    value = condition.get("value", [])
    if value not in (None, []):
        if not str_or_str_list(value):
            errors.append(
                f"{context}: 'has_advanced_tag' requires tags as a string or list when provided."
            )
    return errors


def _validate_rep_at_least(condition: Mapping[str, Any], context: str) -> List[str]:
    errors: List[str] = []
    faction = condition.get("faction")
    value = condition.get("value")
    if not is_non_empty_str(faction):
        errors.append(f"{context}: 'rep_at_least' requires a non-empty string 'faction'.")
    if not isinstance(value, int):
        errors.append(f"{context}: 'rep_at_least' requires an integer 'value'.")
    return errors


def _validate_has_var_gte(condition: Mapping[str, Any], context: str) -> List[str]:
    errors: List[str] = []
    var = condition.get("var")
    value = condition.get("value")
    if not is_non_empty_str(var):
        errors.append(f"{context}: 'has_var_gte' requires a non-empty string 'var'.")
    if not isinstance(value, int):
        errors.append(f"{context}: 'has_var_gte' requires an integer 'value'.")
    return errors


def _validate_rep_at_least_count(condition: Mapping[str, Any], context: str) -> List[str]:
    errors: List[str] = []
    value = condition.get("value")
    count = condition.get("count")
    factions = condition.get("factions")
    if not isinstance(value, int):
        errors.append(f"{context}: 'rep_at_least_count' requires an integer 'value'.")
    if count is not None and not isinstance(count, int):
        errors.append(f"{context}: 'rep_at_least_count' optional 'count' must be an integer if provided.")
    if factions is not None and not str_or_str_list(factions):
        errors.append(
            f"{context}: 'rep_at_least_count' optional 'factions' must be a string or list of strings."
        )
    return errors


def _validate_tick_counter(condition: Mapping[str, Any], context: str, name: str) -> List[str]:
    errors: List[str] = []
    value = condition.get("value")
    if not isinstance(value, int):
        errors.append(f"{context}: '{name}' requires an integer 'value'.")
    return errors


def _validate_time_window(condition: Mapping[str, Any], context: str) -> List[str]:
    errors: List[str] = []
    start = condition.get("start")
    end = condition.get("end")
    if not isinstance(start, int):
        errors.append(f"{context}: 'time_window' requires an integer 'start'.")
    if not isinstance(end, int):
        errors.append(f"{context}: 'time_window' requires an integer 'end'.")
    return errors


def _validate_add_tag(effect: Mapping[str, Any], context: str, name: str) -> List[str]:
    errors: List[str] = []
    value = effect.get("value")
    if not is_non_empty_str(value):
        errors.append(f"{context}: '{name}' requires a non-empty string 'value'.")
    return errors


def _validate_set_flag(effect: Mapping[str, Any], context: str) -> List[str]:
    errors: List[str] = []
    flag = effect.get("flag")
    value = effect.get("value")
    if not is_non_empty_str(flag):
        errors.append(f"{context}: 'set_flag' requires a non-empty string 'flag'.")
    if not simple_value(value):
        errors.append(f"{context}: 'set_flag' requires a simple literal 'value'.")
    return errors


def _validate_set_profile_flag(effect: Mapping[str, Any], context: str) -> List[str]:
    errors: List[str] = []
    flag = effect.get("flag")
    value = effect.get("value")
    if not is_non_empty_str(flag):
        errors.append(f"{context}: 'set_profile_flag' requires a non-empty string 'flag'.")
    if not simple_value(value):
        errors.append(f"{context}: 'set_profile_flag' requires a simple literal 'value'.")
    return errors


def _validate_rep_delta(effect: Mapping[str, Any], context: str) -> List[str]:
    errors: List[str] = []
    faction = effect.get("faction")
    value = effect.get("value")
    if not is_non_empty_str(faction):
        errors.append(f"{context}: 'rep_delta' requires a non-empty string 'faction'.")
    if not isinstance(value, int):
        errors.append(f"{context}: 'rep_delta' requires an integer 'value'.")
    return errors


def _validate_hp_delta(effect: Mapping[str, Any], context: str) -> List[str]:
    errors: List[str] = []
    value = effect.get("value")
    if not isinstance(value, int):
        errors.append(f"{context}: 'hp_delta' requires an integer 'value'.")
    return errors


def _validate_var_value(effect: Mapping[str, Any], context: str, name: str) -> List[str]:
    errors: List[str] = []
    var = effect.get("var")
    value = effect.get("value")
    if not is_non_empty_str(var):
        errors.append(f"{context}: '{name}' requires a non-empty string 'var'.")
    if not isinstance(value, int):
        errors.append(f"{context}: '{name}' requires an integer 'value'.")
    return errors


def _validate_teleport(
    effect: Mapping[str, Any], context: str, nodes: Mapping[str, Any], endings: Mapping[str, Any]
) -> List[str]:
    errors: List[str] = []
    target = effect.get("target")
    if not is_non_empty_str(target):
        errors.append(f"{context}: 'teleport' requires a non-empty string 'target'.")
    elif target not in nodes and target not in endings:
        errors.append(f"{context}: teleport target '{target}' does not exist.")
    return errors


def _validate_end_game(
    effect: Mapping[str, Any], context: str, endings: Mapping[str, Any]
) -> List[str]:
    errors: List[str] = []
    ending = effect.get("value")
    if not is_non_empty_str(ending):
        errors.append(f"{context}: 'end_game' requires a non-empty string 'value'.")
    elif ending not in endings:
        errors.append(f"{context}: ending '{ending}' is not defined.")
    return errors


def _validate_unlock_start(effect: Mapping[str, Any], context: str) -> List[str]:
    errors: List[str] = []
    value = effect.get("value")
    if not is_non_empty_str(value):
        errors.append(f"{context}: 'unlock_start' requires a non-empty string 'value'.")
    return errors


def _validate_grant_legacy_tag(effect: Mapping[str, Any], context: str) -> List[str]:
    errors: List[str] = []
    value = effect.get("value")
    if not is_non_empty_str(value):
        errors.append(f"{context}: 'grant_legacy_tag' requires a non-empty string 'value'.")
    return errors


CONDITION_SPECS: Dict[str, ConditionSpec] = {
    "flag_eq": ConditionSpec(
        required_fields=("flag", "value"),
        optional_fields=(),
        field_rules={"flag": "non-empty string", "value": "simple literal (string/int/bool/null)"},
        validate=_validate_flag_eq,
    ),
    "has_tag": ConditionSpec(
        required_fields=("value",),
        optional_fields=(),
        field_rules={"value": "tag string or non-empty list of tag strings"},
        validate=lambda condition, context: _validate_has_tag(condition, context, "has_tag"),
    ),
    "has_advanced_tag": ConditionSpec(
        required_fields=(),
        optional_fields=("value",),
        field_rules={"value": "optional tag string or list of tag strings"},
        validate=_validate_has_advanced_tag,
    ),
    "has_trait": ConditionSpec(
        required_fields=("value",),
        optional_fields=(),
        field_rules={"value": "trait string or non-empty list of trait strings"},
        validate=lambda condition, context: _validate_has_tag(condition, context, "has_trait"),
    ),
    "missing_tag": ConditionSpec(
        required_fields=("value",),
        optional_fields=(),
        field_rules={"value": "tag string or non-empty list of tag strings"},
        validate=lambda condition, context: _validate_has_tag(condition, context, "missing_tag"),
    ),
    "rep_at_least": ConditionSpec(
        required_fields=("faction", "value"),
        optional_fields=(),
        field_rules={"faction": "non-empty string", "value": "integer reputation threshold"},
        validate=_validate_rep_at_least,
    ),
    "has_var_gte": ConditionSpec(
        required_fields=("var", "value"),
        optional_fields=(),
        field_rules={"var": "non-empty string", "value": "integer resource threshold"},
        validate=_validate_has_var_gte,
    ),
    "rep_at_least_count": ConditionSpec(
        required_fields=("value",),
        optional_fields=("count", "factions"),
        field_rules={
            "value": "integer reputation threshold",
            "count": "optional integer count",
            "factions": "optional faction string or list of faction strings",
        },
        validate=_validate_rep_at_least_count,
    ),
    "profile_flag_eq": ConditionSpec(
        required_fields=("flag", "value"),
        optional_fields=(),
        field_rules={"flag": "non-empty string", "value": "simple literal (string/int/bool/null)"},
        validate=_validate_profile_flag_eq,
    ),
    "profile_flag_is_true": ConditionSpec(
        required_fields=("flag",),
        optional_fields=(),
        field_rules={"flag": "non-empty string"},
        validate=lambda condition, context: _validate_profile_flag_bool(
            condition, context, "profile_flag_is_true"
        ),
    ),
    "profile_flag_is_false": ConditionSpec(
        required_fields=("flag",),
        optional_fields=(),
        field_rules={"flag": "non-empty string"},
        validate=lambda condition, context: _validate_profile_flag_bool(
            condition, context, "profile_flag_is_false"
        ),
    ),
    "tick_counter_at_least": ConditionSpec(
        required_fields=("value",),
        optional_fields=(),
        field_rules={"value": "integer tick counter minimum"},
        validate=lambda condition, context: _validate_tick_counter(
            condition, context, "tick_counter_at_least"
        ),
    ),
    "tick_counter_at_most": ConditionSpec(
        required_fields=("value",),
        optional_fields=(),
        field_rules={"value": "integer tick counter maximum"},
        validate=lambda condition, context: _validate_tick_counter(
            condition, context, "tick_counter_at_most"
        ),
    ),
    "time_window": ConditionSpec(
        required_fields=("start", "end"),
        optional_fields=(),
        field_rules={"start": "integer start hour", "end": "integer end hour"},
        validate=_validate_time_window,
    ),
    "doom_reached": ConditionSpec(
        required_fields=(),
        optional_fields=(),
        field_rules={},
        validate=lambda condition, context: [],
    ),
    "doom_not_reached": ConditionSpec(
        required_fields=(),
        optional_fields=(),
        field_rules={},
        validate=lambda condition, context: [],
    ),
}

EFFECT_SPECS: Dict[str, EffectSpec] = {
    "set_flag": EffectSpec(
        required_fields=("flag", "value"),
        optional_fields=(),
        field_rules={"flag": "non-empty string", "value": "simple literal (string/int/bool/null)"},
        validate=lambda effect, context, nodes, endings: _validate_set_flag(effect, context),
    ),
    "add_tag": EffectSpec(
        required_fields=("value",),
        optional_fields=(),
        field_rules={"value": "non-empty string tag"},
        validate=lambda effect, context, nodes, endings: _validate_add_tag(effect, context, "add_tag"),
    ),
    "remove_tag": EffectSpec(
        required_fields=("value",),
        optional_fields=(),
        field_rules={"value": "non-empty string tag"},
        validate=lambda effect, context, nodes, endings: _validate_add_tag(
            effect, context, "remove_tag"
        ),
    ),
    "add_trait": EffectSpec(
        required_fields=("value",),
        optional_fields=(),
        field_rules={"value": "non-empty string trait"},
        validate=lambda effect, context, nodes, endings: _validate_add_tag(effect, context, "add_trait"),
    ),
    "rep_delta": EffectSpec(
        required_fields=("faction", "value"),
        optional_fields=(),
        field_rules={"faction": "non-empty string", "value": "integer reputation delta"},
        validate=lambda effect, context, nodes, endings: _validate_rep_delta(effect, context),
    ),
    "hp_delta": EffectSpec(
        required_fields=("value",),
        optional_fields=(),
        field_rules={"value": "integer hit point delta"},
        validate=lambda effect, context, nodes, endings: _validate_hp_delta(effect, context),
    ),
    "var_delta": EffectSpec(
        required_fields=("var", "value"),
        optional_fields=(),
        field_rules={"var": "non-empty string", "value": "integer resource delta"},
        validate=lambda effect, context, nodes, endings: _validate_var_value(
            effect, context, "var_delta"
        ),
    ),
    "set_var": EffectSpec(
        required_fields=("var", "value"),
        optional_fields=(),
        field_rules={"var": "non-empty string", "value": "integer resource value"},
        validate=lambda effect, context, nodes, endings: _validate_var_value(
            effect, context, "set_var"
        ),
    ),
    "teleport": EffectSpec(
        required_fields=("target",),
        optional_fields=(),
        field_rules={"target": "non-empty string node or ending id"},
        validate=lambda effect, context, nodes, endings: _validate_teleport(
            effect, context, nodes, endings
        ),
    ),
    "end_game": EffectSpec(
        required_fields=("value",),
        optional_fields=(),
        field_rules={"value": "non-empty string ending id"},
        validate=lambda effect, context, nodes, endings: _validate_end_game(effect, context, endings),
    ),
    "unlock_start": EffectSpec(
        required_fields=("value",),
        optional_fields=(),
        field_rules={"value": "non-empty string start id"},
        validate=lambda effect, context, nodes, endings: _validate_unlock_start(effect, context),
    ),
    "set_profile_flag": EffectSpec(
        required_fields=("flag", "value"),
        optional_fields=(),
        field_rules={"flag": "non-empty string", "value": "simple literal (string/int/bool/null)"},
        validate=lambda effect, context, nodes, endings: _validate_set_profile_flag(
            effect, context
        ),
    ),
    "grant_legacy_tag": EffectSpec(
        required_fields=("value",),
        optional_fields=(),
        field_rules={"value": "non-empty string tag"},
        validate=lambda effect, context, nodes, endings: _validate_grant_legacy_tag(
            effect, context
        ),
    ),
}
