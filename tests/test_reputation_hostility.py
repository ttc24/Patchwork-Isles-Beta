import json
from pathlib import Path

from engine.engine_min import (
    GameState,
    apply_effects,
    load_world,
    resolve_hostile_node,
)
from engine.profile_manager import default_profile
from engine.settings import Settings


def write_world(tmp_path: Path, world: dict) -> Path:
    path = tmp_path / "world.json"
    path.write_text(json.dumps(world))
    return path


def build_state(world: dict, tmp_path: Path) -> GameState:
    path = write_world(tmp_path, world)
    loaded = load_world(path)
    profile = default_profile()
    profile_path = tmp_path / "profile.json"
    profile_path.write_text("{}")
    settings = Settings()
    settings.reduce_animations = True
    return GameState(loaded, profile, profile_path, settings)


def test_rep_delta_applies_ripple(tmp_path: Path) -> None:
    world = {
        "title": "Test",
        "nodes": {"start": {"choices": []}},
        "starts": [{"node": "start"}],
        "faction_relationships": {
            "Wind Choirs": {"Root Court": "enemy", "Skyward": "ally"}
        },
    }
    state = build_state(world, tmp_path)
    apply_effects([{"type": "rep_delta", "faction": "Wind Choirs", "value": 1}], state)
    assert state.player["rep"]["Wind Choirs"] == 1
    assert state.player["rep"]["Root Court"] == -1
    assert state.player["rep"]["Skyward"] == 1


def test_hostile_threshold_routes_to_forced_retreat(tmp_path: Path) -> None:
    world = {
        "title": "Test",
        "nodes": {"start": {"choices": [], "faction": "Root Court"}},
        "starts": [{"node": "start"}],
        "hostile_rep_threshold": -1,
    }
    state = build_state(world, tmp_path)
    state.player["rep"]["Root Court"] = -1
    node = state.world["nodes"]["start"]
    assert resolve_hostile_node(state, "start", node) == "hostile_forced_retreat"
