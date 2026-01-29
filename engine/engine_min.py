#!/usr/bin/env python3
"""
Tag/Trait CYOA Engine — Minimal
- Deterministic: choices are shown only if conditions pass (no greyed-out "teasers").
- Core systems: Tags, Traits, Items, Flags, Faction Reputation (−2..+2).
- No dice, no risk meter, no clocks.
- Save/Load included.
Usage: python3 engine_min.py [world.json]
"""

import hashlib
import json
import os
import sys
import textwrap
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from engine.options_menu import options_menu
    from engine.save_manager import SaveError, SaveManager
    from engine.schema import normalize_nodes, validate_world
    from engine.settings import Settings, load_settings
else:
    from .options_menu import options_menu
    from .save_manager import SaveError, SaveManager
    from .schema import normalize_nodes, validate_world
    from .settings import Settings, load_settings

DEFAULT_WORLD_PATH = "world/world.json"
PROFILE_PATH = "profile.json"
BASE_LINE_WIDTH = 80
MIN_LINE_WIDTH = 50
MAX_LINE_WIDTH = 120

TAG_ALIASES = {
    "Diplomat": "Emissary",
    "Emissary": "Emissary",
    "Judge": "Arbiter",
    "Arbiter": "Arbiter",
}


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


def compute_line_width(settings: Settings) -> int:
    try:
        scale = float(getattr(settings, "ui_scale", 1.0))
    except (TypeError, ValueError):
        scale = 1.0
    width = int(round(BASE_LINE_WIDTH * scale))
    return max(MIN_LINE_WIDTH, min(MAX_LINE_WIDTH, width))


def default_profile():
    return {
        "unlocked_starts": [],
        "legacy_tags": [],
        "seen_endings": [],
        "flags": {},
    }


def load_profile(path=PROFILE_PATH):
    if not os.path.exists(path):
        profile = default_profile()
        save_profile(profile, path)
        return profile
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    data.setdefault("unlocked_starts", [])
    data.setdefault("legacy_tags", [])
    data.setdefault("seen_endings", [])
    data.setdefault("flags", {})

    unlocked = []
    for sid in data["unlocked_starts"]:
        if isinstance(sid, str) and sid not in unlocked:
            unlocked.append(sid)
    data["unlocked_starts"] = unlocked

    data["legacy_tags"] = canonicalize_tag_list(data["legacy_tags"])

    seen = []
    for ending in data["seen_endings"]:
        if isinstance(ending, str) and ending not in seen:
            seen.append(ending)
    data["seen_endings"] = seen

    save_profile(data, path)
    return data


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


def save_profile(profile, path=PROFILE_PATH):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(profile, f, indent=2)
        f.write("\n")


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
            "rep": {},            # faction -> -2..+2
        }
        self.current_node = None
        self.history = []
        self.start_id = None
        self.profile = profile
        self.profile_path = profile_path
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
        if not self.player["rep"]:
            return "—"
        return ", ".join(f"{k}:{v}" for k,v in sorted(self.player["rep"].items()))

    def summary(self):
        inv = ", ".join(self.player["inventory"]) if self.player["inventory"] else "—"
        tags = ", ".join(self.player["tags"]) or "—"
        traits = ", ".join(self.player["traits"]) or "—"
        flags = ", ".join(f"{k}={v}" for k,v in sorted(self.player["flags"].items())) or "—"
        rep = self.rep_str()
        resources = self.player.get("resources", {})
        if isinstance(resources, dict) and resources:
            res = ", ".join(f"{k}:{v}" for k, v in sorted(resources.items()))
        else:
            res = "—"
        return (
            f"HP:{self.player['hp']} | TAGS:[{tags}] | TRAITS:[{traits}] | REP: {rep} | "
            f"INV: {inv} | RES: {res} | FLAGS: {flags}"
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

    for message in updates:
        print(message)

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

    if t == "has_item":
        return cond["value"] in p["inventory"]
    if t == "missing_item":
        return cond["value"] not in p["inventory"]
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
    if t == "has_trait":
        return has_all(p["traits"], cond.get("value"))
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
    return False

# ---------- Effects (minimal set) ----------
def clamp(n, lo, hi): return lo if n<lo else hi if n>hi else n

def apply_effect(effect, state):
    if not effect: return
    t = effect.get("type")
    p = state.player

    if t == "add_item":
        it = effect["value"]
        if it not in p["inventory"]:
            p["inventory"].append(it); print(f"[+] You gain '{it}'.")
    elif t == "remove_item":
        it = effect["value"]
        if it in p["inventory"]:
            p["inventory"].remove(it); print(f"[-] '{it}' removed.")
    elif t == "set_flag":
        p["flags"][effect["flag"]] = effect.get("value", True)
        print(f"[*] Flag {effect['flag']} set to {p['flags'][effect['flag']]}")
    elif t == "add_tag":
        tg = canonical_tag(effect["value"])
        if tg not in p["tags"]:
            p["tags"].append(tg); print(f"[#] New Tag unlocked: {tg}")
        p["tags"] = canonicalize_tag_list(p["tags"])
    elif t == "add_trait":
        tr = effect["value"]
        if tr not in p["traits"]:
            p["traits"].append(tr); print(f"[✦] New Trait gained: {tr}")
    elif t == "rep_delta":
        fac = effect["faction"]; dv = int(effect.get("value",0))
        p["rep"][fac] = clamp(p["rep"].get(fac,0)+dv, -2, 2)
        print(f"[≈] Rep {fac} {'+' if dv>=0 else ''}{dv} -> {p['rep'][fac]}")
    elif t == "hp_delta":
        dv = int(effect.get("value",0))
        p["hp"] += dv; print(f"[♥] HP {'+' if dv>=0 else ''}{dv} -> {p['hp']}")
    elif t == "teleport":
        goto = effect["target"]; print(f"[~] You are moved to '{goto}'."); state.current_node = goto
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
            print(f"[#] Origin unlocked: {title}")
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
            print(f"[Profile] {flag} set to {value}.")
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
            print(f"[#] Legacy Tag granted: {legacy}")

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

def render_node(node, state):
    width = getattr(state, "line_width", BASE_LINE_WIDTH)
    print("\n" + "=" * width)
    print(node.get("title", state.world["title"]))
    print("-" * width)

    body = node.get("text", "")
    if body:
        for paragraph in body.split("\n"):
            if paragraph.strip():
                print(textwrap.fill(paragraph, width=width))
            else:
                print("")
    else:
        print("")

    if node.get("image"):
        print(f"[Image: {node['image']}]")

    print("")
    summary_text = state.summary()
    for line in textwrap.wrap(summary_text, width=width):
        print(line)
    print("-" * width)
    visible = list_choices(node, state)
    for idx, ch in enumerate(visible, start=1):
        print(f"  {idx}. {ch.get('text', f'Choice {idx}')}")
    if state.current_node not in state.world.get("endings", {}):
        commands = [
            "P. Pause",
            "S. Quick Save",
            "L. Quick Load",
            "I. Inventory",
            "T. Tags/Traits",
            "O. Options",
            "Q. Quit",
        ]
        print("  " + "    ".join(commands))
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
        print("Q. Quit")
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

def main():
    world_path = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_WORLD_PATH
    world = load_world(world_path)
    profile = load_profile(PROFILE_PATH)
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
        PROFILE_PATH,
        settings,
        world_seed=world_seed,
        active_area=active_area,
    )
    save_manager = SaveManager(state)

    def open_options_menu():
        updated, changed = options_menu(
            state.settings,
            apply_callback=lambda new_settings: apply_runtime_settings(state, new_settings),
        )
        if changed:
            apply_runtime_settings(state, updated, announce=False)
        return changed

    print(f"=== {world['title']} ===")
    state.player["name"] = input("Name your character: ").strip() or "Traveler"

    # Initialize faction rep
    for fac in world.get("factions", []):
        state.player["rep"][fac] = 0

    # Pick a start and seed starting tags
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

    save_manager.autosave()

    while True:
        node_id = state.current_node
        node = world["nodes"].get(node_id)
        if not node:
            print(f"[!] Missing node '{node_id}'. Exiting."); break

        apply_effects(node.get("on_enter"), state)
        if "__ending__" in state.player["flags"]:
            print(f"\n*** Ending reached: {state.player['flags']['__ending__']} ***"); break

        visible = render_node(node, state)

        save_manager.autosave()

        if node_id in world.get("endings", {}):
            ending_name = world["endings"][node_id]
            record_seen_ending(state, ending_name)
            print(f"\n*** Ending reached: {ending_name} ***"); break

        choice = input("> ").strip().lower()
        if choice == "q":
            print("Goodbye!"); break
        if choice == "p":
            action = pause_menu(state, save_manager, open_options_menu)
            if action == "quit":
                print("Goodbye!"); break
            if action == "loaded":
                save_manager.autosave()
            continue
        if choice == "i":
            print("Inventory:", ", ".join(state.player["inventory"]) or "Empty"); continue
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
            print("Enter a number or P/S/L/I/T/O/Q."); continue
        idx = int(choice)
        if not (1 <= idx <= len(visible)):
            print("Pick a valid choice number."); continue

        ch = visible[idx-1]
        apply_effects(ch.get("effects"), state)
        if "__ending__" in state.player["flags"]:
            print(f"\n*** Ending reached: {state.player['flags']['__ending__']} ***"); break

        target = ch.get("target")
        if not target:
            print("[!] Choice had no target; staying put."); continue

        state.record_transition(node_id, target, ch.get("text","choice"))
        state.current_node = target

        if state.player["hp"] <= 0:
            demise = "A Short Tale"
            record_seen_ending(state, demise)
            print(f"\n*** You have perished. Ending: '{demise}' ***"); break

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n[Interrupted] Bye.")
