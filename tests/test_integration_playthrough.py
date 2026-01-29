import random
from pathlib import Path

from engine.engine_min import (
    GameState,
    apply_effects,
    canonicalize_tag_list,
    list_choices,
    load_world,
    record_seen_ending,
)
from engine.profile_manager import default_profile, save_profile
from engine.settings import Settings


def pick_start(world: dict, profile: dict) -> tuple[str, list[str]]:
    unlocked = set(profile.get("unlocked_starts", []))
    for entry in world.get("starts", []):
        start_id = entry.get("id") or entry.get("node")
        if entry.get("locked") and start_id not in unlocked:
            continue
        return entry.get("node", "start"), canonicalize_tag_list(entry.get("tags", []))
    return "start", []


def simulate_random_playthrough(state: GameState, *, seed: int, max_steps: int = 2000) -> str:
    rng = random.Random(seed)
    steps = 0
    while steps < max_steps:
        steps += 1
        node_id = state.current_node
        node = state.world["nodes"].get(node_id)
        assert node is not None, f"Missing node '{node_id}'."

        apply_effects(node.get("on_enter"), state)
        if "__ending__" in state.player["flags"]:
            return state.player["flags"]["__ending__"]

        if node_id in state.world.get("endings", {}):
            ending_name = state.world["endings"][node_id]
            record_seen_ending(state, ending_name)
            return ending_name

        visible = list_choices(node, state)
        assert visible, f"No available choices from node '{node_id}'."

        choice = rng.choice(visible)
        apply_effects(choice.get("effects"), state)
        if "__ending__" in state.player["flags"]:
            return state.player["flags"]["__ending__"]

        target = choice.get("target")
        if target:
            state.record_transition(node_id, target, choice.get("text", "choice"))
            state.current_node = target
        if state.player["hp"] <= 0:
            demise = "A Short Tale"
            record_seen_ending(state, demise)
            return demise

    raise AssertionError(f"Playthrough exceeded {max_steps} steps without reaching an ending.")


def test_random_playthrough_reaches_ending(tmp_path: Path) -> None:
    world = load_world("world/world.json")
    profile = default_profile()
    profile_path = tmp_path / "profile.json"
    save_profile(profile, profile_path)

    settings = Settings()
    settings.reduce_animations = True

    state = GameState(
        world,
        profile,
        profile_path,
        settings,
        world_seed=0,
        active_area=world.get("title") or "Unknown",
    )
    start_node, start_tags = pick_start(world, profile)
    state.current_node = start_node
    state.start_id = start_node
    state.player["tags"] = canonicalize_tag_list(start_tags)

    ending = simulate_random_playthrough(state, seed=0)
    assert ending
