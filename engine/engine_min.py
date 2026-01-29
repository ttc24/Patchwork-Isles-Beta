#!/usr/bin/env python3
"""
Tag/Trait CYOA Engine — Minimal
- Deterministic: choices are shown only if conditions pass (no greyed-out "teasers").
- Core systems: Tags, Traits, Items, Flags, Faction Reputation (−10..+10).
- No dice, no risk meter, no clocks.
- Save/Load included.
Usage: python3 engine_min.py [world.json]
"""

import argparse
import asyncio
import hashlib
import json
import re
import sys
import textwrap
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from engine.options_menu import options_menu
    from engine.platform import IS_WEB
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
    from .platform import IS_WEB
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


def emit_print(*args, **kwargs) -> None:
    print(*args, **kwargs)


async def read_input(prompt: str = "") -> str:
    return await asyncio.to_thread(input, prompt)

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

    if IS_WEB:
        return INLINE_FORMAT_PATTERN.sub(lambda match: match.group(2), text)

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
    if not isinstance(profile.get("flags"), dict):
        profile["flags"] = {}
    profile["tick_counter"] = normalize_tick_counter(profile.get("tick_counter", 0))
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


async def emit_line(text: str, state: "GameState", *, allow_delay: bool = True) -> None:
    delay = compute_text_delay(state.settings) if allow_delay else 0.0
    formatted = print_formatted(text)
    if delay <= 0:
        emit_print(formatted)
        return
    for char in formatted:
        emit_print(char, end="", flush=True)
        await asyncio.sleep(delay)
    emit_print("")


async def emit_effect_message(
    state: "GameState", message: str, *, audio_cue: str | None = None
) -> None:
    await emit_line(print_formatted(message), state, allow_delay=True)
    if audio_cue and getattr(state.settings, "caption_audio_cues", False):
        await emit_line(print_formatted(f"[Audio Cue] {audio_cue}"), state, allow_delay=True)


def read_world_art(state: "GameState", filename: str | None) -> str | None:
    if not isinstance(filename, str) or not filename.strip():
        return None
    try:
        world_path = Path(getattr(state, "world_path", DEFAULT_WORLD_PATH)).resolve()
    except (OSError, RuntimeError):
        world_path = Path(DEFAULT_WORLD_PATH).resolve()
    art_dir = world_path.parent / "art"
    requested_path = Path(filename)
    if requested_path.is_absolute() or ".." in requested_path.parts:
        return None
    art_path = (art_dir / requested_path).resolve()
    try:
        art_dir_resolved = art_dir.resolve()
    except FileNotFoundError:
        art_dir_resolved = art_dir
    if art_path != art_dir_resolved and art_dir_resolved not in art_path.parents:
        return None
    try:
        return art_path.read_text(encoding="utf-8")
    except OSError:
        return None


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


async def apply_runtime_settings(
    state: GameState, new_settings: Settings, *, announce: bool = True
) -> Settings:
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
        await emit_line(message, state, allow_delay=True)

    return state.settings

def _raise_world_validation(errors):
    raise ValueError("Invalid world.json:\n- " + "\n- ".join(errors))


def _merge_world_modules(world, world_path):
    modules = world.get("modules")
    if not modules:
        return world
    if not isinstance(modules, list):
        _raise_world_validation(["'modules' must be a list of module file paths."])

    base_nodes, node_errors = normalize_nodes(world.get("nodes"))
    if node_errors:
        _raise_world_validation(node_errors)
    base_endings = world.get("endings") or {}
    if not isinstance(base_endings, dict):
        _raise_world_validation(["'endings' must be an object mapping ending IDs to text."])
    base_starts = world.get("starts") or []
    if not isinstance(base_starts, list):
        _raise_world_validation(["'starts' must be a list of start entries."])

    combined_nodes = dict(base_nodes)
    combined_endings = dict(base_endings)
    combined_starts = list(base_starts)
    base_dir = Path(world_path).resolve().parent

    for module_ref in modules:
        if not isinstance(module_ref, str) or not module_ref.strip():
            _raise_world_validation(["module entries must be non-empty strings."])
        module_path = (base_dir / module_ref).resolve()
        with open(module_path, "r", encoding="utf-8") as handle:
            module = json.load(handle)
        if not isinstance(module, dict):
            _raise_world_validation([f"{module_path}: module data must be a JSON object."])

        module_nodes, module_node_errors = normalize_nodes(module.get("nodes"))
        if module_node_errors:
            _raise_world_validation([f"{module_path}: {err}" for err in module_node_errors])
        overlap = set(combined_nodes).intersection(module_nodes)
        if overlap:
            _raise_world_validation(
                [f"{module_path}: node IDs already exist in base world: {', '.join(sorted(overlap))}."]
            )
        combined_nodes.update(module_nodes)

        module_endings = module.get("endings") or {}
        if not isinstance(module_endings, dict):
            _raise_world_validation([f"{module_path}: 'endings' must be an object."])
        for ending_id, ending_text in module_endings.items():
            if ending_id in combined_endings and combined_endings[ending_id] != ending_text:
                _raise_world_validation(
                    [
                        f"{module_path}: ending '{ending_id}' conflicts with existing definition.",
                    ]
                )
            combined_endings.setdefault(ending_id, ending_text)

        module_starts = module.get("starts") or []
        if not isinstance(module_starts, list):
            _raise_world_validation([f"{module_path}: 'starts' must be a list."])
        combined_starts.extend(module_starts)

    world["nodes"] = combined_nodes
    world["endings"] = combined_endings
    world["starts"] = combined_starts
    return world


def load_world(path):
    with open(path, "r", encoding="utf-8") as f:
        world = json.load(f)
    if not isinstance(world, dict):
        _raise_world_validation(["World data must be a JSON object."])

    world = _merge_world_modules(world, path)

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
        if not getattr(state.settings, "doom_clock_enabled", True):
            return False
        return doom_reached(state.tick_counter)
    if t == "doom_not_reached":
        if not getattr(state.settings, "doom_clock_enabled", True):
            return True
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


async def resolve_hostile_node(state, node_id, node):
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
        await emit_effect_message(
            state,
            f"[!] Hostile presence from {', '.join(hostile)} forces a {outcome.replace('_', ' ')}.",
            audio_cue="Hostile encounter.",
        )
    return target


async def apply_rep_delta_with_ripple(state, faction, delta):
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
        await emit_effect_message(
            state,
            f"[≈] Rep {fac} {'+' if dv>=0 else ''}{dv} -> {state.player['rep'][fac]}",
            audio_cue="Reputation changed.",
        )

async def apply_effect(effect, state):
    if not effect: return
    t = effect.get("type")
    p = state.player

    if t == "set_flag":
        p["flags"][effect["flag"]] = effect.get("value", True)
        await emit_effect_message(
            state,
            f"[*] Flag {effect['flag']} set to {p['flags'][effect['flag']]}",
            audio_cue="Status updated.",
        )
    elif t == "add_tag":
        tg = canonical_tag(effect["value"])
        if tg not in p["tags"]:
            p["tags"].append(tg)
            await emit_effect_message(
                state, f"[#] New Tag unlocked: {tg}", audio_cue="Tag unlocked."
            )
        p["tags"] = canonicalize_tag_list(p["tags"])
    elif t == "remove_tag":
        tg = canonical_tag(effect["value"])
        if tg in p["tags"]:
            p["tags"].remove(tg)
            await emit_effect_message(
                state, f"[#] Tag removed: {tg}", audio_cue="Tag removed."
            )
        p["tags"] = canonicalize_tag_list(p["tags"])
    elif t == "add_trait":
        tr = effect["value"]
        if tr not in p["traits"]:
            p["traits"].append(tr)
            await emit_effect_message(
                state, f"[✦] New Trait gained: {tr}", audio_cue="Trait gained."
            )
    elif t == "var_delta":
        var = effect.get("var")
        if not var:
            return
        dv = int(effect.get("value", 0))
        p["resources"][var] = p["resources"].get(var, 0) + dv
        await emit_effect_message(
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
        await emit_effect_message(
            state,
            f"[¤] {var} set to {p['resources'][var]}",
            audio_cue="Resources updated.",
        )
    elif t == "rep_delta":
        fac = effect["faction"]
        dv = int(effect.get("value", 0))
        await apply_rep_delta_with_ripple(state, fac, dv)
    elif t == "hp_delta":
        dv = int(effect.get("value",0))
        p["hp"] += dv
        await emit_effect_message(
            state,
            f"[♥] HP {'+' if dv>=0 else ''}{dv} -> {p['hp']}",
            audio_cue="Health changed.",
        )
    elif t == "teleport":
        goto = effect["target"]
        await emit_effect_message(
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
            await emit_effect_message(
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
            await emit_effect_message(
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
            await emit_effect_message(
                state,
                f"[#] Legacy Tag granted: {legacy}",
                audio_cue="Legacy tag granted.",
            )

async def apply_effects(effects, state):
    for eff in effects or []:
        await apply_effect(eff, state)

# ---------- Loop ----------
def list_choices(node, state):
    visible = []
    for ch in node.get("choices", []):
        if meets_condition(ch.get("condition"), state):
            visible.append(ch)
    return visible


def resolve_choice_target(choice, state):
    target = choice.get("target")
    if isinstance(target, str) and target:
        return target
    if isinstance(target, list):
        for entry in target:
            if not isinstance(entry, dict):
                continue
            if meets_condition(entry.get("condition"), state):
                entry_target = entry.get("target")
                if isinstance(entry_target, str) and entry_target:
                    return entry_target
    return None


def resolve_action_type(choice, current_node, state):
    action = choice.get("action")
    if isinstance(action, str) and action in ACTION_TICK_COSTS:
        return action
    target = resolve_choice_target(choice, state)
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

def summarize_choice_requirements(condition):
    if not condition:
        return "None"
    if isinstance(condition, list):
        parts = []
        for entry in condition:
            summary = summarize_choice_requirements(entry)
            if summary and summary != "None":
                parts.append(summary)
        return ", ".join(parts) if parts else "None"
    if not isinstance(condition, dict):
        return "None"
    ctype = condition.get("type")
    if ctype in {"has_tag", "has_trait"}:
        labels = extract_choice_requirement_labels(condition)
        if not labels:
            return "None"
        label_name = "Tags" if ctype == "has_tag" else "Traits"
        return f"{label_name}: {'/'.join(labels)}"
    if ctype == "has_advanced_tag":
        value = condition.get("value")
        if value is None:
            return "Advanced Tags"
        tags = value if isinstance(value, list) else [value]
        tags = [tag for tag in canonicalize_tag_list(tags) if tag]
        return f"Advanced Tags: {'/'.join(tags)}" if tags else "Advanced Tags"
    if ctype == "missing_tag":
        value = condition.get("value")
        if value is None:
            return "Missing Tag"
        tags = value if isinstance(value, list) else [value]
        tags = [tag for tag in canonicalize_tag_list(tags) if tag]
        return f"Missing Tags: {'/'.join(tags)}" if tags else "Missing Tag"
    if ctype == "flag_eq":
        flag = condition.get("flag")
        value = condition.get("value")
        if flag is None:
            return "Flag"
        return f"Flag {flag}={value}"
    if ctype == "profile_flag_eq":
        flag = condition.get("flag")
        value = condition.get("value")
        if flag is None:
            return "Profile Flag"
        return f"Profile Flag {flag}={value}"
    if ctype == "profile_flag_is_true":
        flag = condition.get("flag")
        return f"Profile Flag {flag}=True" if flag else "Profile Flag True"
    if ctype == "profile_flag_is_false":
        flag = condition.get("flag")
        return f"Profile Flag {flag}=False" if flag else "Profile Flag False"
    if ctype == "has_var_gte":
        var = condition.get("var")
        value = condition.get("value")
        if not var:
            return "Resource >=?"
        return f"Resource {var}>={value}"
    if ctype == "rep_at_least":
        faction = condition.get("faction")
        value = condition.get("value")
        if faction is None:
            return f"Rep >= {value}"
        return f"Rep {faction}>={value}"
    if ctype == "rep_at_least_count":
        value = condition.get("value")
        count = condition.get("count")
        return f"Rep>={value} in {count}+ factions"
    if ctype == "tick_counter_at_least":
        return f"Ticks>={condition.get('value')}"
    if ctype == "tick_counter_at_most":
        return f"Ticks<={condition.get('value')}"
    if ctype == "time_window":
        start = condition.get("start")
        end = condition.get("end")
        return f"Time {start}-{end}"
    if ctype == "doom_reached":
        return "Doom Reached"
    if ctype == "doom_not_reached":
        return "Doom Not Reached"
    return "None"

async def render_node(node, state):
    width = getattr(state, "line_width", BASE_LINE_WIDTH)
    settings = state.settings
    emit_print("\n" + separator(width, settings, primary=True))
    emit_print(format_heading(node.get("title", state.world["title"]), settings))
    emit_print(separator(width, settings, primary=False))

    art_text = read_world_art(state, node.get("art"))
    if art_text:
        for line in art_text.splitlines():
            await emit_line(line, state, allow_delay=True)
        emit_print("")

    body = node.get("text", "")
    if body:
        for paragraph in body.split("\n"):
                    if paragraph.strip():
                        for line in textwrap.wrap(paragraph, width=width):
                            await emit_line(line, state, allow_delay=True)
                    else:
                        emit_print("")
    else:
        emit_print("")

    if node.get("image"):
        await emit_line(f"[Image: {node['image']}]", state, allow_delay=True)

    emit_print("")
    summary_text = state.summary()
    if getattr(settings, "high_contrast", False):
        summary_text = f"STATUS: {summary_text}"
    for line in textwrap.wrap(summary_text, width=width):
        await emit_line(line, state, allow_delay=True)
    emit_print(separator(width, settings, primary=False))
    visible = list_choices(node, state)
    for idx, ch in enumerate(visible, start=1):
        choice_text = ch.get("text", f"Choice {idx}")
        requirement_labels = extract_choice_requirement_labels(ch.get("condition"))
        if requirement_labels:
            joined_labels = "/".join(requirement_labels)
            choice_text = f"[{joined_labels}] {choice_text}"
        if getattr(state, "debug", False):
            target = resolve_choice_target(ch, state) or "None"
            requirement_summary = summarize_choice_requirements(ch.get("condition"))
            choice_text = f"{choice_text} (Target: {target} | Req: {requirement_summary})"
        choice_text = format_choice_text(choice_text, settings)
        choice_text = print_formatted(choice_text)
        if getattr(settings, "high_contrast", False):
            emit_print(f"  [{idx}] {choice_text}")
        else:
            emit_print(f"  {idx}. {choice_text}")
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
        emit_print(commands_line)
        if getattr(state, "debug", False):
            debug_line = "  DEBUG: /goto, /give, /set"
            if getattr(settings, "high_contrast", False):
                debug_line = "  DEBUG COMMANDS: /goto, /give, /set"
            emit_print(debug_line)
    return visible

async def pick_start(world, profile, open_options=None):
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
        emit_print("Choose your origin:")
        display = []
        index = 0

        def show_group(title, entries):
            nonlocal index
            if not entries:
                return
            emit_print(title)
            for sid, start in entries:
                index += 1
                display.append((sid, start))
                tags = canonicalize_tag_list(start.get("tags", []))
                tag_str = ", ".join(tags) if tags else "—"
                node = start.get("node", "?")
                emit_print(
                    f"  {index}. {start.get('title','Start')} (Node: {node} | Tags: {tag_str})"
                )
                blurb = start.get("blurb")
                if blurb:
                    for line in blurb.splitlines():
                        emit_print(f"     {line}")
                else:
                    emit_print("     —")
            emit_print("")

        show_group("Core Starts (always available):", core)
        show_group("Unlocked Starts (profile):", unlocked)

        if not display:
            return "start", [], None

        if open_options is not None:
            emit_print("  O. Options")

        selection = (await read_input("> ")).strip().lower()
        if selection in {"o", "options"} and open_options is not None:
            await open_options()
            emit_print("")
            continue
        if selection.isdigit():
            i = int(selection)
            if 1 <= i <= len(display):
                sid, start = display[i - 1]
                tags = canonicalize_tag_list(start.get("tags", []))
                return start["node"], tags, sid
        if open_options is not None:
            emit_print("Pick a valid number or press O for options.")
        else:
            emit_print("Pick a valid number.")

def show_slot_overview(save_manager):
    slots = save_manager.list_slots()
    if not slots:
        emit_print("No manual saves recorded yet.")
        return
    emit_print("Available saves:")
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
            emit_print(f"  - {meta.slot}: {info}")
        else:
            emit_print(f"  - {meta.slot}")


async def prompt_slot_name(action, save_manager):
    show_slot_overview(save_manager)
    raw = (await read_input(f"Enter slot name to {action} (blank to cancel): ")).strip()
    if not raw:
        emit_print(f"{action.title()} cancelled.")
        return None
    return raw


async def pause_menu(state, save_manager, open_options=None):
    while True:
        emit_print("\n=== Pause Menu ===")
        emit_print("1. Save Game")
        emit_print("2. Load Game")
        emit_print("3. Quick Save")
        emit_print("4. Quick Load")
        if open_options is not None:
            emit_print("5. Options")
        emit_print("R. Resume")
        emit_print("Q. Quit to Title")
        choice = (await read_input("> ")).strip().lower()

        if choice in {"r", "resume"}:
            return "resume"
        if choice in {"q", "quit"}:
            return "quit"
        if choice == "1":
            slot = await prompt_slot_name("save", save_manager)
            if not slot:
                continue
            try:
                save_manager.save(slot)
            except SaveError as exc:
                emit_print(f"[!] {exc}")
            continue
        if choice == "2":
            slot = await prompt_slot_name("load", save_manager)
            if not slot:
                continue
            try:
                if await save_manager.load(slot):
                    return "loaded"
            except SaveError as exc:
                emit_print(f"[!] {exc}")
            continue
        if choice == "3":
            save_manager.save(save_manager.QUICK_SLOT, label="Quick Save")
            continue
        if choice == "4":
            if await save_manager.load(save_manager.QUICK_SLOT):
                return "loaded"
            continue
        if choice == "5" and open_options is not None:
            await open_options()
            continue
        emit_print("Pick a valid pause option.")

async def show_history(state, page_size=5):
    entries = list(reversed(state.history))
    if not entries:
        emit_print("No history yet.")
        return
    total_pages = max(1, (len(entries) + page_size - 1) // page_size)
    page = 0
    while True:
        start = page * page_size
        end = start + page_size
        page_entries = entries[start:end]
        emit_print(f"\n=== History (Page {page + 1}/{total_pages}) ===")
        for idx, entry in enumerate(page_entries, start=start + 1):
            origin = entry.get("from") or "?"
            target = entry.get("to") or "?"
            choice = entry.get("choice") or "—"
            emit_print(f"{idx}. {origin} -> {target} | {choice}")
        emit_print("N. Next  P. Previous  Q. Back")
        selection = (await read_input("> ")).strip().lower()
        if selection in {"q", "back", "quit"}:
            return
        if selection in {"n", "next"}:
            if page + 1 < total_pages:
                page += 1
            else:
                emit_print("Already at the last page.")
            continue
        if selection in {"p", "prev", "previous"}:
            if page > 0:
                page -= 1
            else:
                emit_print("Already at the first page.")
            continue
        emit_print("Pick N, P, or Q.")


async def prompt_quit_to_title(save_manager):
    while True:
        response = (
            await read_input("Save before returning to title? (y/n, or c to cancel): ")
        ).strip().lower()
        if response in {"c", "cancel"}:
            return False
        if response in {"n", "no"}:
            return True
        if response in {"y", "yes"}:
            slot = await prompt_slot_name("save", save_manager)
            if not slot:
                return False
            try:
                save_manager.save(slot)
            except SaveError as exc:
                emit_print(f"[!] {exc}")
                return False
            return True
        emit_print("Enter Y, N, or C.")

async def main():
    parser = argparse.ArgumentParser(description="Run the minimal CYOA engine.")
    parser.add_argument("world", nargs="?", default=DEFAULT_WORLD_PATH)
    parser.add_argument("--debug", action="store_true", help="Enable debug commands.")
    args = parser.parse_args()
    world_path = args.world
    debug_mode = args.debug
    world = load_world(world_path)
    selection = await select_profile()
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
    state.debug = debug_mode
    state.world_path = world_path

    async def open_options_menu():
        updated, changed = await options_menu(
            state.settings,
            apply_callback=lambda new_settings: apply_runtime_settings(state, new_settings),
        )
        if changed:
            await apply_runtime_settings(state, updated, announce=False)
        return changed

    async def initialize_run():
        nonlocal state
        state = GameState(
            world,
            profile,
            selection.profile_path,
            settings,
            world_seed=world_seed,
            active_area=active_area,
        )
        state.world_path = world_path
        state.debug = debug_mode
        emit_print(f"\n=== {world['title']} ===")
        emit_print(f"[Profile] {selection.name}")
        state.player["name"] = (await read_input("Name your character: ")).strip() or "Traveler"

        for fac in world.get("factions", []):
            state.player["rep"][fac] = 0

        start_node, start_tags, start_id = await pick_start(world, profile, open_options_menu)
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
            emit_print(f"[#] Legacy Tags active this run: {', '.join(newly_applied)}")

        return SaveManager(state, base_path=selection.save_root)

    while True:
        save_manager = await initialize_run()
        save_manager.autosave()

        while True:
            node_id = state.current_node
            node = world["nodes"].get(node_id)
            if not node:
                emit_print(f"[!] Missing node '{node_id}'. Exiting."); return

            hostile_target = await resolve_hostile_node(state, node_id, node)
            if hostile_target:
                state.current_node = hostile_target
                continue

            await apply_effects(node.get("on_enter"), state)
            if "__ending__" in state.player["flags"]:
                emit_print(f"\n*** Ending reached: {state.player['flags']['__ending__']} ***"); return

            visible = await render_node(node, state)

            save_manager.autosave()

            if node_id in world.get("endings", {}):
                ending_name = world["endings"][node_id]
                record_seen_ending(state, ending_name)
                emit_print(f"\n*** Ending reached: {ending_name} ***"); return

            raw_choice = (await read_input("> ")).strip()
            choice = raw_choice.lower()
            if state.debug and raw_choice.startswith("/"):
                parts = raw_choice.split()
                command = parts[0].lower()
                if command == "/goto":
                    if len(parts) < 2:
                        emit_print("Usage: /goto <node_id>")
                        continue
                    target = parts[1]
                    if target in world.get("nodes", {}) or target in world.get("endings", {}):
                        state.current_node = target
                        await emit_line(f"[#] Debug: moved to {target}.", state, allow_delay=False)
                    else:
                        emit_print(f"[!] Unknown node '{target}'.")
                    continue
                if command == "/give":
                    if len(parts) < 2:
                        emit_print("Usage: /give <tag_name>")
                        continue
                    tag = canonical_tag(" ".join(parts[1:]).strip())
                    state.player["tags"].append(tag)
                    state.player["tags"] = canonicalize_tag_list(state.player["tags"])
                    await emit_effect_message(state, f"[#] Debug: Tag granted: {tag}")
                    continue
                if command == "/set":
                    if len(parts) < 3:
                        emit_print("Usage: /set <faction> <amount>")
                        continue
                    faction = parts[1]
                    try:
                        amount = int(parts[2])
                    except ValueError:
                        emit_print("Amount must be an integer.")
                        continue
                    amount = max(DEFAULT_REP_MIN, min(DEFAULT_REP_MAX, amount))
                    state.player.setdefault("rep", {})[faction] = amount
                    await emit_effect_message(
                        state,
                        f"[#] Debug: {faction} reputation set to {amount}.",
                    )
                    continue
                emit_print("Unknown debug command.")
                continue
            if choice == "q":
                if await prompt_quit_to_title(save_manager):
                    break
                continue
            if choice == "p":
                action = await pause_menu(state, save_manager, open_options_menu)
                if action == "quit":
                    if await prompt_quit_to_title(save_manager):
                        break
                    continue
                if action == "loaded":
                    save_manager.autosave()
                continue
            if choice == "h":
                await show_history(state); continue
            if choice == "i":
                emit_print("Traits:", ", ".join(state.player["traits"]) or "—")
                emit_print("Key Items:", ", ".join(state.player["tags"]) or "—")
                emit_print("Supplies:", format_resources(state.player.get("resources", {})))
                emit_print("Reputation:", format_reputation_display(state.player.get("rep", {})))
                continue
            if choice == "t":
                emit_print("Tags:", ", ".join(state.player["tags"]) or "—")
                emit_print("Traits:", ", ".join(state.player["traits"]) or "—"); continue
            if choice == "s":
                try:
                    save_manager.save(save_manager.QUICK_SLOT, label="Quick Save")
                except SaveError as exc:
                    emit_print(f"[!] {exc}")
                continue
            if choice == "l":
                if await save_manager.load(save_manager.QUICK_SLOT):
                    save_manager.autosave()
                continue
            if choice == "o":
                await open_options_menu(); continue
            if not choice.isdigit():
                emit_print("Enter a number or P/S/L/I/H/O/Q."); continue
            idx = int(choice)
            if not (1 <= idx <= len(visible)):
                emit_print("Pick a valid choice number."); continue

            ch = visible[idx-1]
            action_type = resolve_action_type(ch, node_id, state)
            if getattr(state.settings, "doom_clock_enabled", True):
                state.tick_counter = increment_ticks(state.tick_counter, action_type)
            await apply_effects(ch.get("effects"), state)
            if "__ending__" in state.player["flags"]:
                emit_print(f"\n*** Ending reached: {state.player['flags']['__ending__']} ***"); return

            target = resolve_choice_target(ch, state)
            if not target:
                emit_print("[!] Choice had no target; staying put."); continue

            state.record_transition(node_id, target, ch.get("text","choice"))
            state.current_node = target

            if state.player["hp"] <= 0:
                demise = "A Short Tale"
                record_seen_ending(state, demise)
                emit_print(f"\n*** You have perished. Ending: '{demise}' ***"); return

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        emit_print("\n[Interrupted] Bye.")
