#!/usr/bin/env python3
"""
Tag/Trait CYOA Engine — Minimal
- Deterministic: choices are shown only if conditions pass (no greyed-out "teasers").
- Core systems: Tags, Traits, Items, Flags, Faction Reputation (−10..+10).
- No dice, no risk meter, no clocks.
- Save/Load included.
Usage: python3 engine_min.py [world.json]
"""

import hashlib
import json
import re
import sys
import textwrap
import time
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from engine.options_menu import options_menu
    from engine.profile_manager import load_profile, save_profile, select_profile
    from engine.save_manager import SaveError, SaveManager
    from engine.schema import normalize_nodes, validate_world
    from engine.settings import Settings, load_settings
    from engine.timekeeping import (
        ACTION_TICK_COSTS,
        doom_reached,
        increment_ticks,
        is_time_window,
        normalize_tick_counter,
    )
else:
    from .options_menu import options_menu
    from .profile_manager import load_profile, save_profile, select_profile
    from .save_manager import SaveError, SaveManager
    from .schema import normalize_nodes, validate_world
    from .settings import Settings, load_settings
    from .timekeeping import (
        ACTION_TICK_COSTS,
        doom_reached,
        increment_ticks,
        is_time_window,
        normalize_tick_counter,
    )

DEFAULT_WORLD_PATH = "world/world.json"
BASE_LINE_WIDTH = 80
MIN_LINE_WIDTH = 50
MAX_LINE_WIDTH = 120
BASE_TEXT_DELAY = 0.02

TAG_ALIASES = {
    "Diplomat": "Emissary",
    "Emissary": "Emissary",
    "Judge": "Arbiter",
    "Arbiter": "Arbiter",
}

ANSI_RESET = "\033[0m"

DEFAULT_REP_MIN = -10
DEFAULT_REP_MAX = 10
REPUTATION_TIERS = [
    (-10, -8, "Nemesis"),
    (-7, -5, "Hated"),
    (-4, -2, "Wary"),
    (-1, 1, "Neutral"),
    (2, 4, "Favored"),
    (5, 7, "Trusted"),
    (8, 10, "Exalted"),
]
INLINE_COLOR_MAP = {
    "trait": "\033[36m",
    "traits": "\033[36m",
    "tag": "\033[32m",
    "tags": "\033[32m",
    "item": "\033[32m",
    "items": "\033[32m",
    "resource": "\033[32m",
    "resources": "\033[32m",
    "faction": "\033[33m",
    "factions": "\033[33m",
    "locked": "\033[31m",
    "danger": "\033[31m",
}
INLINE_FORMAT_PATTERN = re.compile(r"\{([a-zA-Z_]+):([^}]+)\}")


def print_formatted(text: str) -> str:
    if not text or "{" not in text:
        return text

    def replace(match: re.Match[str]) -> str:
        kind = match.group(1).strip().lower()
        value = match.group(2)
        color = INLINE_COLOR_MAP.get(kind)
        if not color:
            return value
        return f"{color}{value}{ANSI_RESET}"

    return INLINE_FORMAT_PATTERN.sub(replace, text)


def canonical_tag(tag):
    return TAG_ALIASES.get(tag, tag)


def canonicalize_tag_list(tags):
    seen = []
    for tag in tags or []:
        ctag = canonical_tag(tag)
        if ctag not in seen:
            seen.append(ctag)
    return seen


def canonicalize_tag_value(value):
    if isinstance(value, list):
        return [canonical_tag(v) for v in value]
    if isinstance(value, str):
        return canonical_tag(value)
    return value


def normalize_profile(profile):
    unlocked = []
    for sid in profile.get("unlocked_starts", []):
        if isinstance(sid, str) and sid not in unlocked:
            unlocked.append(sid)
    profile["unlocked_starts"] = unlocked

    profile["legacy_tags"] = canonicalize_tag_list(profile.get("legacy_tags", []))

    seen = []
    for ending in profile.get("seen_endings", []):
        if isinstance(ending, str) and ending not in seen:
            seen.append(ending)
    profile["seen_endings"] = seen
    return profile


def format_resources(resources, *, empty: str = "—") -> str:
    if not isinstance(resources, dict) or not resources:
        return empty
    parts = []
    for key, value in sorted(resources.items()):
        label = str(key).title()
        parts.append(f"{value} {label}")
    return ", ".join(parts) if parts else empty


def compute_line_width(settings: Settings) -> int:
    try:
        scale = float(getattr(settings, "ui_scale", 1.0))
    except (TypeError, ValueError):
        scale = 1.0
    width = int(round(BASE_LINE_WIDTH * scale))
    return max(MIN_LINE_WIDTH, min(MAX_LINE_WIDTH, width))


def compute_text_delay(settings: Settings) -> float:
    try:
        speed = float(getattr(settings, "text_speed", 1.0))
    except (TypeError, ValueError):
        speed = 1.0
    if getattr(settings, "reduce_animations", False):
        return 0.0
    if speed <= 0:
        return 0.0
    return BASE_TEXT_DELAY / max(speed, 0.1)


def emit_line(text: str, state: "GameState", *, allow_delay: bool = True) -> None:
    delay = compute_text_delay(state.settings) if allow_delay else 0.0
    formatted = print_formatted(text)
    if delay <= 0:
        print(formatted)
        return
    for char in formatted:
        print(char, end="", flush=True)
        time.sleep(delay)
    print("")


def emit_effect_message(state: "GameState", message: str, *, audio_cue: str | None = None) -> None:
    emit_line(print_formatted(message), state, allow_delay=True)
    if audio_cue and getattr(state.settings, "caption_audio_cues", False):
        emit_line(print_formatted(f"[Audio Cue] {audio_cue}"), state, allow_delay=True)


def format_heading(text: str, settings: Settings) -> str:
    return text.upper() if getattr(settings, "high_contrast", False) else text


def format_choice_text(text: str, settings: Settings) -> str:
    return text.upper() if getattr(settings, "high_contrast", False) else text


def separator(width: int, settings: Settings, *, primary: bool) -> str:
    if getattr(settings, "high_contrast", False):
        char = "#" if primary else "="
    else:
        char = "=" if primary else "-"
    return char * width


def merge_profile_starts(world, profile):
    starts = world.setdefault("starts", [])
    if not isinstance(starts, list):
        return

    unlocked_ids = set(profile.get("unlocked_starts", []))
    for entry in starts:
        if not isinstance(entry, dict):
            continue
        sid = entry.get("id") or entry.get("node")
        if sid in unlocked_ids:
            entry.pop("locked", None)


def record_seen_ending(state, ending_name):
    if not ending_name:
        return
    seen = state.profile.setdefault("seen_endings", [])
    if ending_name not in seen:
        seen.append(ending_name)
        save_profile(state.profile, state.profile_path)


class GameState:
    def __init__(
        self,
        world,
        profile,
        profile_path,
        settings=None,
        *,
        world_seed=None,
        active_area=None,
    ):
        self.world = world
        self.player = {
            "name": None,
            "hp": 10,
            "tags": [],           # e.g., ["Sneaky","Diplomat"]
            "traits": [],         # e.g., ["People-Reader"]
            "inventory": [],
            "resources": {},      # e.g., {"gold": 5}
            "flags": {},          # story state
            "rep": {},            # faction -> -10..+10
        }
        self.current_node = None
        self.history = []
        self.start_id = None
        self.profile = profile
        self.profile_path = profile_path
        self.tick_counter = normalize_tick_counter(
            profile.get("tick_counter", 0) if isinstance(profile, dict) else 0
        )
        self.settings = Settings()
        self.line_width = BASE_LINE_WIDTH
        self.window_mode = "windowed"
        self.vsync_enabled = True
        self.audio_levels = {"master": 1.0, "music": 1.0, "sfx": 1.0}
        self.world_seed = world_seed if world_seed is not None else 0
        self.active_area = active_area or world.get("title") or "Unknown"

        if settings is None:
            settings = Settings()
        self.apply_settings(settings)
        self.ensure_consistency()

    def rep_str(self):
        return format_reputation_display(self.player["rep"])

    def summary(self):
        tags = ", ".join(self.player["tags"]) or "—"
        traits = ", ".join(self.player["traits"]) or "—"
        flags = ", ".join(f"{k}={v}" for k,v in sorted(self.player["flags"].items())) or "—"
        rep = self.rep_str()
        res = format_resources(self.player.get("resources", {}))
        return (
            f"HP:{self.player['hp']} | KEY ITEMS:[{tags}] | TRAITS:[{traits}] | REP: {rep} | "
            f"SUPPLIES: {res} | FLAGS: {flags}"
        )

    def apply_settings(self, settings):
        if isinstance(settings, Settings):
            sanitized = settings.copy()
        else:
            sanitized = Settings()
        sanitized.clamp()
        self.settings = sanitized
        self.line_width = compute_line_width(sanitized)
        self.window_mode = sanitized.window_mode
        self.vsync_enabled = sanitized.vsync
        self.audio_levels = {
            "master": sanitized.audio_master,
            "music": sanitized.audio_music,
            "sfx": sanitized.audio_sfx,
        }

    def ensure_consistency(self):
        player = self.player or {}
        if not isinstance(player, dict):
            player = {}
        player.setdefault("name", None)
        player.setdefault("hp", 10)
        player.setdefault("tags", [])
        player.setdefault("traits", [])
        player.setdefault("inventory", [])
        player.setdefault("resources", {})
        player.setdefault("flags", {})
        player.setdefault("rep", {})
        if not isinstance(player["inventory"], list):
            player["inventory"] = list(player["inventory"])
        if not isinstance(player["tags"], list):
            player["tags"] = list(player["tags"])
        if not isinstance(player["traits"], list):
            player["traits"] = list(player["traits"])
        if not isinstance(player["flags"], dict):
            player["flags"] = {}
        if not isinstance(player["rep"], dict):
            player["rep"] = {}
        if not isinstance(player["resources"], dict):
            player["resources"] = {}
        player["tags"] = canonicalize_tag_list(player.get("tags", []))
        self.player = player

        normalized_history = []
        if isinstance(self.history, list):
            for entry in self.history:
                if isinstance(entry, dict):
                    origin = entry.get("from")
                    target = entry.get("to")
                    choice = entry.get("choice")
                elif isinstance(entry, (list, tuple)) and len(entry) >= 3:
                    origin, target, choice = entry[:3]
                else:
                    continue
                normalized_history.append(
                    {
                        "from": origin,
                        "to": target,
                        "choice": choice,
                    }
                )
        self.history = normalized_history
        if not isinstance(self.start_id, str):
            self.start_id = self.start_id or None
        if not isinstance(self.active_area, str) or not self.active_area:
            self.active_area = self.world.get("title") or "Unknown"
        if not isinstance(self.world_seed, int):
            try:
                self.world_seed = int(self.world_seed)
            except (TypeError, ValueError):
                self.world_seed = 0
        self.tick_counter = normalize_tick_counter(getattr(self, "tick_counter", 0))

    def record_transition(self, origin, target, choice_text):
        entry = {
            "from": origin,
            "to": target,
            "choice": choice_text,
        }
        self.history.append(entry)


def apply_runtime_settings(state: GameState, new_settings: Settings, *, announce: bool = True) -> Settings:
    if isinstance(new_settings, Settings):
        target = new_settings.copy()
    else:
        target = Settings()
    target.clamp()

    previous = state.settings.copy()
    state.apply_settings(target)

    if not announce:
        return state.settings

    updates = []
    if (
        previous.audio_master != state.settings.audio_master
        or previous.audio_music != state.settings.audio_music
        or previous.audio_sfx != state.settings.audio_sfx
    ):
        updates.append(
            "[Audio] Master {0:.0f}% | Music {1:.0f}% | SFX {2:.0f}%".format(
                state.settings.audio_master * 100,
                state.settings.audio_music * 100,
                state.settings.audio_sfx * 100,
            )
        )
    if previous.window_mode != state.settings.window_mode:
        updates.append(f"[Display] Window mode set to {state.settings.window_mode.title()}.")
    if previous.vsync != state.settings.vsync:
        updates.append(
            f"[Display] VSync {'enabled' if state.settings.vsync else 'disabled'}."
        )
    if previous.ui_scale != state.settings.ui_scale:
        updates.append(
            f"[UI] Scale adjusted to {state.settings.ui_scale:.2f}x (line width {state.line_width})."
        )
    if previous.text_speed != state.settings.text_speed:
        if state.settings.text_speed <= 0:
            updates.append("[UI] Text speed set to instant.")
        else:
            updates.append(f"[UI] Text speed set to {state.settings.text_speed:.2f}x.")
    if previous.high_contrast != state.settings.high_contrast:
        updates.append(
            f"[Accessibility] High contrast {'enabled' if state.settings.high_contrast else 'disabled'}."
        )
    if previous.reduce_animations != state.settings.reduce_animations:
        updates.append(
            f"[Accessibility] Reduce animations {'enabled' if state.settings.reduce_animations else 'disabled'}."
        )
    if previous.caption_audio_cues != state.settings.caption_audio_cues:
        updates.append(
            "[Accessibility] Caption audio cues "
            f"{'enabled' if state.settings.caption_audio_cues else 'disabled'}."
        )

    for message in updates:
        emit_line(message, state, allow_delay=True)

    return state.settings

def _raise_world_validation(errors):
    raise ValueError("Invalid world.json:\n- " + "\n- ".join(errors))


def load_world(path):
    with open(path, "r", encoding="utf-8") as f:
        world = json.load(f)
    if not isinstance(world, dict):
        _raise_world_validation(["World data must be a JSON object."])

    errors = validate_world(world)
    if errors:
        _raise_world_validation(errors)

    nodes, node_errors = normalize_nodes(world.get("nodes"))
    if node_errors:
        _raise_world_validation(node_errors)
    world["nodes"] = nodes
    world.setdefault("starts", [])
    world.setdefault("endings", {})
    world.setdefault("factions", [])
    world.setdefault("advanced_tags", [])
    world.setdefault("faction_relationships", {})
    world.setdefault("faction_relationship_multipliers", {})
    world.setdefault("hostile_rep_threshold", -5)
    world.setdefault("faction_hostile_thresholds", {})
    world.setdefault(
        "hostile_outcomes",
        {"game_over": "hostile_game_over", "forced_retreat": "hostile_forced_retreat"},
    )
    world.setdefault("default_hostile_outcome", "forced_retreat")
    ensure_hostile_outcome_nodes(world)
    return world


def get_start_title(world, start_id):
    for start in world.get("starts", []):
        sid = start.get("id") or start.get("node")
        if sid == start_id:
            return start.get("title") or start_id
    return start_id

# ---------- Conditions (minimal set) ----------
def has_all(player_list, value):
    if isinstance(value, str):
        return value in player_list
    return all(v in player_list for v in value)

def meets_condition(cond, state):
    if not cond:
        return True
    if isinstance(cond, list):
        return all(meets_condition(c, state) for c in cond)
    t = cond.get("type")
    p = state.player

    if t == "flag_eq":
        return p["flags"].get(cond["flag"]) == cond.get("value")
    if t == "has_tag":
        required = canonicalize_tag_value(cond.get("value"))
        player_tags = set(canonicalize_tag_list(p["tags"]))
        if isinstance(required, list):
            return all(r in player_tags for r in required)
        return required in player_tags
    if t == "has_advanced_tag":
        world_adv = canonicalize_tag_list(state.world.get("advanced_tags", []))
        requested = cond.get("value")
        if requested is None:
            required = world_adv
        else:
            required = canonicalize_tag_list(requested if isinstance(requested, list) else [requested])
        if not required:
            return False
        player_tags = set(canonicalize_tag_list(p["tags"]))
        return any(r in player_tags for r in required)
    if t == "missing_tag":
        required = canonicalize_tag_value(cond.get("value"))
        player_tags = set(canonicalize_tag_list(p["tags"]))
        if isinstance(required, list):
            return all(r not in player_tags for r in required)
        return required not in player_tags
    if t == "has_trait":
        return has_all(p["traits"], cond.get("value"))
    if t == "has_var_gte":
        var = cond.get("var")
        if not var:
            return False
        value = int(cond.get("value", 0))
        return p["resources"].get(var, 0) >= value
    if t == "rep_at_least":
        return p["rep"].get(cond["faction"], 0) >= int(cond["value"])
    if t == "rep_at_least_count":
        value = int(cond.get("value", 0))
        count = int(cond.get("count", 1))
        factions = cond.get("factions")
        if isinstance(factions, str):
            factions = [factions]
        factions = factions or state.world.get("factions", [])
        met = sum(1 for fac in factions if p["rep"].get(fac, 0) >= value)
        return met >= count
    if t == "profile_flag_eq":
        flags = state.profile.get("flags", {})
        return flags.get(cond.get("flag")) == cond.get("value")
    if t == "profile_flag_is_true":
        flags = state.profile.get("flags", {})
        return bool(flags.get(cond.get("flag")))
    if t == "profile_flag_is_false":
        flags = state.profile.get("flags", {})
        return not bool(flags.get(cond.get("flag")))
    if t == "tick_counter_at_least":
        return normalize_tick_counter(state.tick_counter) >= int(cond.get("value", 0))
    if t == "tick_counter_at_most":
        return normalize_tick_counter(state.tick_counter) <= int(cond.get("value", 0))
    if t == "time_window":
        start = cond.get("start", 0)
        end = cond.get("end", 0)
        return is_time_window(state.tick_counter, int(start), int(end))
    if t == "doom_reached":
        return doom_reached(state.tick_counter)
    if t == "doom_not_reached":
        return not doom_reached(state.tick_counter)
    return False

# ---------- Effects (minimal set) ----------
def clamp(n, lo, hi): return lo if n < lo else hi if n > hi else n


def get_rep_bounds(world):
    if not isinstance(world, dict):
        return DEFAULT_REP_MIN, DEFAULT_REP_MAX
    bounds = world.get("rep_bounds")
    if isinstance(bounds, dict):
        rep_min = bounds.get("min", DEFAULT_REP_MIN)
        rep_max = bounds.get("max", DEFAULT_REP_MAX)
    else:
        rep_min = world.get("rep_min", DEFAULT_REP_MIN)
        rep_max = world.get("rep_max", DEFAULT_REP_MAX)
    try:
        rep_min = int(rep_min)
        rep_max = int(rep_max)
    except (TypeError, ValueError):
        return DEFAULT_REP_MIN, DEFAULT_REP_MAX
    if rep_min > rep_max:
        rep_min, rep_max = rep_max, rep_min
    return rep_min, rep_max


def rep_tier_label(value, tiers=REPUTATION_TIERS):
    try:
        rep_value = int(value)
    except (TypeError, ValueError):
        rep_value = 0
    for low, high, label in tiers:
        if low <= rep_value <= high:
            return label
    if tiers:
        return tiers[0][2] if rep_value < tiers[0][0] else tiers[-1][2]
    return "Neutral"


def format_reputation_display(rep_map):
    if not isinstance(rep_map, dict) or not rep_map:
        return "—"
    parts = []
    for faction, value in sorted(rep_map.items()):
        try:
            rep_value = int(value)
        except (TypeError, ValueError):
            rep_value = 0
        label = rep_tier_label(rep_value)
        parts.append(f"{faction}: {label} ({rep_value:+d})")
    return ", ".join(parts)


def get_relationship_multipliers(world):
    defaults = {"ally": 1, "enemy": -1}
    custom = world.get("faction_relationship_multipliers", {})
    if isinstance(custom, dict):
        defaults.update({k: v for k, v in custom.items() if isinstance(v, int)})
    return defaults


def normalize_faction_list(value):
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        return [v for v in value if isinstance(v, str) and v.strip()]
    return []


def get_node_factions(node):
    if not isinstance(node, dict):
        return []
    factions = normalize_faction_list(node.get("factions"))
    faction = node.get("faction")
    if isinstance(faction, str) and faction.strip():
        factions.append(faction)
    return list(dict.fromkeys(factions))


def get_hostile_threshold(world, faction):
    overrides = world.get("faction_hostile_thresholds", {})
    if isinstance(overrides, dict) and faction in overrides and isinstance(overrides[faction], int):
        return overrides[faction]
    return world.get("hostile_rep_threshold", -5)


def get_hostile_outcome_targets(world):
    targets = world.get("hostile_outcomes", {})
    if isinstance(targets, dict):
        return targets
    return {}


def ensure_hostile_outcome_nodes(world):
    nodes = world.get("nodes", {})
    endings = world.get("endings", {})
    targets = get_hostile_outcome_targets(world)
    defaults = {
        "hostile_game_over": {
            "title": "Hostile Encounter",
            "text": "Your reputation turns the welcome into a wall of drawn steel. "
            "The path ends here under a chorus of denied passage.",
            "choices": [],
            "ignore_hostile": True,
        },
        "hostile_forced_retreat": {
            "title": "Forced Retreat",
            "text": "Cold stares and raised voices force you back from the threshold. "
            "You retreat to regroup, the route closed for now.",
            "choices": [],
            "ignore_hostile": True,
        },
    }
    for key, node_id in targets.items():
        if not isinstance(node_id, str) or not node_id:
            continue
        if node_id not in nodes and node_id in defaults:
            nodes[node_id] = defaults[node_id]
        if key == "game_over":
            endings.setdefault(node_id, "Hostile Encounter")
        elif key == "forced_retreat":
            endings.setdefault(node_id, "Forced Retreat")
    world["nodes"] = nodes
    world["endings"] = endings


def resolve_hostile_node(state, node_id, node):
    if not isinstance(node, dict):
        return None
    if node.get("ignore_hostile"):
        return None
    outcome_targets = get_hostile_outcome_targets(state.world)
    if node_id in outcome_targets.values():
        return None
    factions = get_node_factions(node)
    if not factions:
        return None
    hostile = []
    for faction in factions:
        threshold = get_hostile_threshold(state.world, faction)
        if state.player["rep"].get(faction, 0) <= threshold:
            hostile.append(faction)
    if not hostile:
        return None
    outcome = node.get("hostile_outcome") or state.world.get("default_hostile_outcome")
    if outcome not in {"game_over", "forced_retreat"}:
        outcome = "forced_retreat"
    target = outcome_targets.get(outcome)
    if target:
        emit_effect_message(
            state,
            f"[!] Hostile presence from {', '.join(hostile)} forces a {outcome.replace('_', ' ')}.",
            audio_cue="Hostile encounter.",
        )
    return target


def apply_rep_delta_with_ripple(state, faction, delta):
    updates = {faction: delta}
    relationships = state.world.get("faction_relationships", {})
    if isinstance(relationships, dict):
        for other, relation in relationships.get(faction, {}).items():
            if not isinstance(other, str) or not isinstance(relation, str):
                continue
            multiplier = get_relationship_multipliers(state.world).get(relation)
            if multiplier is None:
                continue
            updates[other] = updates.get(other, 0) + delta * multiplier
    rep_min, rep_max = get_rep_bounds(state.world)
    for fac, dv in updates.items():
        if dv == 0:
            continue
        state.player["rep"][fac] = clamp(state.player["rep"].get(fac, 0) + dv, rep_min, rep_max)
        emit_effect_message(
            state,
            f"[≈] Rep {fac} {'+' if dv>=0 else ''}{dv} -> {state.player['rep'][fac]}",
            audio_cue="Reputation changed.",
        )

def apply_effect(effect, state):
    if not effect: return
    t = effect.get("type")
    p = state.player

    if t == "set_flag":
        p["flags"][effect["flag"]] = effect.get("value", True)
        emit_effect_message(
            state,
            f"[*] Flag {effect['flag']} set to {p['flags'][effect['flag']]}",
            audio_cue="Status updated.",
        )
    elif t == "add_tag":
        tg = canonical_tag(effect["value"])
        if tg not in p["tags"]:
            p["tags"].append(tg)
            emit_effect_message(state, f"[#] New Tag unlocked: {tg}", audio_cue="Tag unlocked.")
        p["tags"] = canonicalize_tag_list(p["tags"])
    elif t == "remove_tag":
        tg = canonical_tag(effect["value"])
        if tg in p["tags"]:
            p["tags"].remove(tg)
            emit_effect_message(state, f"[#] Tag removed: {tg}", audio_cue="Tag removed.")
        p["tags"] = canonicalize_tag_list(p["tags"])
    elif t == "add_trait":
        tr = effect["value"]
        if tr not in p["traits"]:
            p["traits"].append(tr)
            emit_effect_message(state, f"[✦] New Trait gained: {tr}", audio_cue="Trait gained.")
    elif t == "var_delta":
        var = effect.get("var")
        if not var:
            return
        dv = int(effect.get("value", 0))
        p["resources"][var] = p["resources"].get(var, 0) + dv
        emit_effect_message(
            state,
            f"[¤] {var} {'+' if dv >= 0 else ''}{dv} -> {p['resources'][var]}",
            audio_cue="Resources updated.",
        )
    elif t == "set_var":
        var = effect.get("var")
        if not var:
            return
        value = int(effect.get("value", 0))
        p["resources"][var] = value
        emit_effect_message(
            state,
            f"[¤] {var} set to {p['resources'][var]}",
            audio_cue="Resources updated.",
        )
    elif t == "rep_delta":
        fac = effect["faction"]
        dv = int(effect.get("value", 0))
        apply_rep_delta_with_ripple(state, fac, dv)
    elif t == "hp_delta":
        dv = int(effect.get("value",0))
        p["hp"] += dv
        emit_effect_message(
            state,
            f"[♥] HP {'+' if dv>=0 else ''}{dv} -> {p['hp']}",
            audio_cue="Health changed.",
        )
    elif t == "teleport":
        goto = effect["target"]
        emit_effect_message(
            state,
            f"[~] You are moved to '{goto}'.",
            audio_cue="Location transition.",
        )
        state.current_node = goto
    elif t == "end_game":
        p["flags"]["__ending__"] = effect.get("value", "Unnamed Ending")
        record_seen_ending(state, p["flags"]["__ending__"])
    elif t == "unlock_start":
        start_id = effect.get("value")
        if not start_id:
            return
        unlocked = state.profile.setdefault("unlocked_starts", [])
        if start_id not in unlocked:
            unlocked.append(start_id)
            save_profile(state.profile, state.profile_path)
            title = get_start_title(state.world, start_id)
            emit_effect_message(
                state,
                f"[#] Origin unlocked: {title}",
                audio_cue="Origin unlocked.",
            )
        merge_profile_starts(state.world, state.profile)
    elif t == "set_profile_flag":
        flag = effect.get("flag")
        if not flag:
            return
        flags = state.profile.setdefault("flags", {})
        value = effect.get("value", True)
        previous = flags.get(flag)
        if previous != value:
            flags[flag] = value
            save_profile(state.profile, state.profile_path)
            emit_effect_message(
                state,
                f"[Profile] {flag} set to {value}.",
                audio_cue="Profile updated.",
            )
        else:
            flags[flag] = value
    elif t == "grant_legacy_tag":
        legacy = canonical_tag(effect.get("value"))
        if not legacy:
            return
        tags = state.profile.setdefault("legacy_tags", [])
        if legacy not in tags:
            tags.append(legacy)
            save_profile(state.profile, state.profile_path)
            emit_effect_message(
                state,
                f"[#] Legacy Tag granted: {legacy}",
                audio_cue="Legacy tag granted.",
            )

def apply_effects(effects, state):
    for eff in effects or []:
        apply_effect(eff, state)

# ---------- Loop ----------
def list_choices(node, state):
    visible = []
    for ch in node.get("choices", []):
        if meets_condition(ch.get("condition"), state):
            visible.append(ch)
    return visible


def resolve_action_type(choice, current_node):
    action = choice.get("action")
    if isinstance(action, str) and action in ACTION_TICK_COSTS:
        return action
    target = choice.get("target")
    if target and target != current_node:
        return "move"
    return "explore"

def extract_choice_requirement_labels(condition):
    if not condition:
        return []
    if isinstance(condition, list):
        labels = []
        for entry in condition:
            labels.extend(extract_choice_requirement_labels(entry))
        return labels
    if not isinstance(condition, dict):
        return []
    ctype = condition.get("type")
    if ctype == "has_tag":
        value = condition.get("value")
        if value is None:
            return []
        tags = value if isinstance(value, list) else [value]
        return [tag for tag in canonicalize_tag_list(tags) if tag]
    if ctype == "has_trait":
        value = condition.get("value")
        if value is None:
            return []
        traits = value if isinstance(value, list) else [value]
        return [str(trait) for trait in traits if trait]
    return []

def render_node(node, state):
    width = getattr(state, "line_width", BASE_LINE_WIDTH)
    settings = state.settings
    print("\n" + separator(width, settings, primary=True))
    print(format_heading(node.get("title", state.world["title"]), settings))
    print(separator(width, settings, primary=False))

    body = node.get("text", "")
    if body:
        for paragraph in body.split("\n"):
            if paragraph.strip():
                for line in textwrap.wrap(paragraph, width=width):
                    emit_line(line, state, allow_delay=True)
            else:
                print("")
    else:
        print("")

    if node.get("image"):
        emit_line(f"[Image: {node['image']}]", state, allow_delay=True)

    print("")
    summary_text = state.summary()
    if getattr(settings, "high_contrast", False):
        summary_text = f"STATUS: {summary_text}"
    for line in textwrap.wrap(summary_text, width=width):
        emit_line(line, state, allow_delay=True)
    print(separator(width, settings, primary=False))
    visible = list_choices(node, state)
    for idx, ch in enumerate(visible, start=1):
        choice_text = ch.get("text", f"Choice {idx}")
        requirement_labels = extract_choice_requirement_labels(ch.get("condition"))
        if requirement_labels:
            joined_labels = "/".join(requirement_labels)
            choice_text = f"[{joined_labels}] {choice_text}"
        choice_text = format_choice_text(choice_text, settings)
        choice_text = print_formatted(choice_text)
        if getattr(settings, "high_contrast", False):
            print(f"  [{idx}] {choice_text}")
        else:
            print(f"  {idx}. {choice_text}")
    if state.current_node not in state.world.get("endings", {}):
        commands = [
            "P. Pause",
            "S. Quick Save",
            "L. Quick Load",
            "I. Status",
            "H. History",
            "O. Options",
            "Q. Quit to Title",
        ]
        commands_line = "  " + "    ".join(commands)
        if getattr(settings, "high_contrast", False):
            commands_line = "  COMMANDS: " + " | ".join(commands)
        print(commands_line)
    return visible

def pick_start(world, profile, open_options=None):
    starts = world.get("starts", [])
    unlocked_ids = set(profile.get("unlocked_starts", []))
    core = []
    unlocked = []
    for s in starts:
        start_id = s.get("id") or s.get("node")
        if s.get("locked") and start_id not in unlocked_ids:
            continue
        entry = (start_id, s)
        if s.get("locked"):
            unlocked.append(entry)
        else:
            core.append(entry)
    if not (core or unlocked):
        return "start", [], None

    while True:
        print("Choose your origin:")
        display = []
        index = 0

        def show_group(title, entries):
            nonlocal index
            if not entries:
                return
            print(title)
            for sid, start in entries:
                index += 1
                display.append((sid, start))
                tags = canonicalize_tag_list(start.get("tags", []))
                tag_str = ", ".join(tags) if tags else "—"
                node = start.get("node", "?")
                print(
                    f"  {index}. {start.get('title','Start')} (Node: {node} | Tags: {tag_str})"
                )
                blurb = start.get("blurb")
                if blurb:
                    for line in blurb.splitlines():
                        print(f"     {line}")
                else:
                    print("     —")
            print("")

        show_group("Core Starts (always available):", core)
        show_group("Unlocked Starts (profile):", unlocked)

        if not display:
            return "start", [], None

        if open_options is not None:
            print("  O. Options")

        selection = input("> ").strip().lower()
        if selection in {"o", "options"} and open_options is not None:
            open_options()
            print("")
            continue
        if selection.isdigit():
            i = int(selection)
            if 1 <= i <= len(display):
                sid, start = display[i - 1]
                tags = canonicalize_tag_list(start.get("tags", []))
                return start["node"], tags, sid
        if open_options is not None:
            print("Pick a valid number or press O for options.")
        else:
            print("Pick a valid number.")

def show_slot_overview(save_manager):
    slots = save_manager.list_slots()
    if not slots:
        print("No manual saves recorded yet.")
        return
    print("Available saves:")
    for meta in slots:
        details = []
        if meta.player_name:
            details.append(meta.player_name)
        if meta.active_area:
            details.append(f"@ {meta.active_area}")
        if meta.saved_at:
            details.append(meta.saved_at)
        info = " ".join(details)
        if info:
            print(f"  - {meta.slot}: {info}")
        else:
            print(f"  - {meta.slot}")


def prompt_slot_name(action, save_manager):
    show_slot_overview(save_manager)
    raw = input(f"Enter slot name to {action} (blank to cancel): ").strip()
    if not raw:
        print(f"{action.title()} cancelled.")
        return None
    return raw


def pause_menu(state, save_manager, open_options=None):
    while True:
        print("\n=== Pause Menu ===")
        print("1. Save Game")
        print("2. Load Game")
        print("3. Quick Save")
        print("4. Quick Load")
        if open_options is not None:
            print("5. Options")
        print("R. Resume")
        print("Q. Quit to Title")
        choice = input("> ").strip().lower()

        if choice in {"r", "resume"}:
            return "resume"
        if choice in {"q", "quit"}:
            return "quit"
        if choice == "1":
            slot = prompt_slot_name("save", save_manager)
            if not slot:
                continue
            try:
                save_manager.save(slot)
            except SaveError as exc:
                print(f"[!] {exc}")
            continue
        if choice == "2":
            slot = prompt_slot_name("load", save_manager)
            if not slot:
                continue
            try:
                if save_manager.load(slot):
                    return "loaded"
            except SaveError as exc:
                print(f"[!] {exc}")
            continue
        if choice == "3":
            save_manager.save(save_manager.QUICK_SLOT, label="Quick Save")
            continue
        if choice == "4":
            if save_manager.load(save_manager.QUICK_SLOT):
                return "loaded"
            continue
        if choice == "5" and open_options is not None:
            open_options()
            continue
        print("Pick a valid pause option.")

def show_history(state, page_size=5):
    entries = list(reversed(state.history))
    if not entries:
        print("No history yet.")
        return
    total_pages = max(1, (len(entries) + page_size - 1) // page_size)
    page = 0
    while True:
        start = page * page_size
        end = start + page_size
        page_entries = entries[start:end]
        print(f"\n=== History (Page {page + 1}/{total_pages}) ===")
        for idx, entry in enumerate(page_entries, start=start + 1):
            origin = entry.get("from") or "?"
            target = entry.get("to") or "?"
            choice = entry.get("choice") or "—"
            print(f"{idx}. {origin} -> {target} | {choice}")
        print("N. Next  P. Previous  Q. Back")
        selection = input("> ").strip().lower()
        if selection in {"q", "back", "quit"}:
            return
        if selection in {"n", "next"}:
            if page + 1 < total_pages:
                page += 1
            else:
                print("Already at the last page.")
            continue
        if selection in {"p", "prev", "previous"}:
            if page > 0:
                page -= 1
            else:
                print("Already at the first page.")
            continue
        print("Pick N, P, or Q.")


def prompt_quit_to_title(save_manager):
    while True:
        response = input("Save before returning to title? (y/n, or c to cancel): ").strip().lower()
        if response in {"c", "cancel"}:
            return False
        if response in {"n", "no"}:
            return True
        if response in {"y", "yes"}:
            slot = prompt_slot_name("save", save_manager)
            if not slot:
                return False
            try:
                save_manager.save(slot)
            except SaveError as exc:
                print(f"[!] {exc}")
                return False
            return True
        print("Enter Y, N, or C.")

def main():
    world_path = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_WORLD_PATH
    world = load_world(world_path)
    selection = select_profile()
    profile = load_profile(selection.profile_path)
    profile = normalize_profile(profile)
    save_profile(profile, selection.profile_path)
    merge_profile_starts(world, profile)
    settings = load_settings()
    world_seed = world.get("seed") if isinstance(world, dict) else None
    if isinstance(world_seed, str):
        try:
            world_seed = int(world_seed, 0)
        except ValueError:
            world_seed = None
    if not isinstance(world_seed, int):
        digest = hashlib.sha1(world_path.encode("utf-8")).hexdigest()
        world_seed = int(digest[:8], 16)
    active_area = world.get("title") if isinstance(world, dict) else "Unknown"
    state = GameState(
        world,
        profile,
        selection.profile_path,
        settings,
        world_seed=world_seed,
        active_area=active_area,
    )

    def open_options_menu():
        updated, changed = options_menu(
            state.settings,
            apply_callback=lambda new_settings: apply_runtime_settings(state, new_settings),
        )
        if changed:
            apply_runtime_settings(state, updated, announce=False)
        return changed

    def initialize_run():
        nonlocal state
        state = GameState(
            world,
            profile,
            selection.profile_path,
            settings,
            world_seed=world_seed,
            active_area=active_area,
        )
        print(f"\n=== {world['title']} ===")
        print(f"[Profile] {selection.name}")
        state.player["name"] = input("Name your character: ").strip() or "Traveler"

        for fac in world.get("factions", []):
            state.player["rep"][fac] = 0

        start_node, start_tags, start_id = pick_start(world, profile, open_options_menu)
        state.current_node = start_node
        state.start_id = start_id or start_node
        for t in canonicalize_tag_list(start_tags):
            if t not in state.player["tags"]:
                state.player["tags"].append(t)
        state.player["tags"] = canonicalize_tag_list(state.player["tags"])

        legacy_tags = canonicalize_tag_list(profile.get("legacy_tags", []))
        newly_applied = []
        for t in legacy_tags:
            if t not in state.player["tags"]:
                state.player["tags"].append(t)
                newly_applied.append(t)
        state.player["tags"] = canonicalize_tag_list(state.player["tags"])
        if newly_applied:
            print(f"[#] Legacy Tags active this run: {', '.join(newly_applied)}")

        return SaveManager(state, base_path=selection.save_root)

    while True:
        save_manager = initialize_run()
        save_manager.autosave()

        while True:
            node_id = state.current_node
            node = world["nodes"].get(node_id)
            if not node:
                print(f"[!] Missing node '{node_id}'. Exiting."); return

            hostile_target = resolve_hostile_node(state, node_id, node)
            if hostile_target:
                state.current_node = hostile_target
                continue

            apply_effects(node.get("on_enter"), state)
            if "__ending__" in state.player["flags"]:
                print(f"\n*** Ending reached: {state.player['flags']['__ending__']} ***"); return

            visible = render_node(node, state)

            save_manager.autosave()

            if node_id in world.get("endings", {}):
                ending_name = world["endings"][node_id]
                record_seen_ending(state, ending_name)
                print(f"\n*** Ending reached: {ending_name} ***"); return

            choice = input("> ").strip().lower()
            if choice == "q":
                if prompt_quit_to_title(save_manager):
                    break
                continue
            if choice == "p":
                action = pause_menu(state, save_manager, open_options_menu)
                if action == "quit":
                    if prompt_quit_to_title(save_manager):
                        break
                    continue
                if action == "loaded":
                    save_manager.autosave()
                continue
            if choice == "h":
                show_history(state); continue
            if choice == "i":
                print("Traits:", ", ".join(state.player["traits"]) or "—")
                print("Key Items:", ", ".join(state.player["tags"]) or "—")
                print("Supplies:", format_resources(state.player.get("resources", {})))
                print("Reputation:", format_reputation_display(state.player.get("rep", {})))
                continue
            if choice == "t":
                print("Tags:", ", ".join(state.player["tags"]) or "—")
                print("Traits:", ", ".join(state.player["traits"]) or "—"); continue
            if choice == "s":
                try:
                    save_manager.save(save_manager.QUICK_SLOT, label="Quick Save")
                except SaveError as exc:
                    print(f"[!] {exc}")
                continue
            if choice == "l":
                if save_manager.load(save_manager.QUICK_SLOT):
                    save_manager.autosave()
                continue
            if choice == "o":
                open_options_menu(); continue
            if not choice.isdigit():
                print("Enter a number or P/S/L/I/H/O/Q."); continue
            idx = int(choice)
            if not (1 <= idx <= len(visible)):
                print("Pick a valid choice number."); continue

            ch = visible[idx-1]
            action_type = resolve_action_type(ch, node_id)
            state.tick_counter = increment_ticks(state.tick_counter, action_type)
            apply_effects(ch.get("effects"), state)
            if "__ending__" in state.player["flags"]:
                print(f"\n*** Ending reached: {state.player['flags']['__ending__']} ***"); return

            target = ch.get("target")
            if not target:
                print("[!] Choice had no target; staying put."); continue

            state.record_transition(node_id, target, ch.get("text","choice"))
            state.current_node = target

            if state.player["hp"] <= 0:
                demise = "A Short Tale"
                record_seen_ending(state, demise)
                print(f"\n*** You have perished. Ending: '{demise}' ***"); return

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n[Interrupted] Bye.")
