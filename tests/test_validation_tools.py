import json
import subprocess
import sys
from pathlib import Path

import pytest

from engine.engine_min import load_world
from engine.schema import normalize_nodes
from tools import list_unreachable


REPO_ROOT = Path(__file__).resolve().parents[1]


def write_world(tmp_path: Path, world: dict) -> Path:
    path = tmp_path / "world.json"
    path.write_text(json.dumps(world))
    return path


@pytest.mark.parametrize(
    ("world", "match"),
    [
        ({"nodes": {}}, "title"),
        ({"title": "Test", "nodes": "nope"}, "nodes"),
        ({"title": "Test", "nodes": [{"title": "No id"}]}, "missing"),
    ],
)
def test_load_world_rejects_invalid_shapes(tmp_path: Path, world: dict, match: str) -> None:
    path = write_world(tmp_path, world)
    with pytest.raises(ValueError, match=match):
        load_world(path)


def test_normalize_nodes_rejects_duplicate_list_ids() -> None:
    _, errors = normalize_nodes(
        [
            {"id": "dup", "title": "First"},
            {"id": "dup", "title": "Second"},
        ]
    )
    assert any("Duplicate node IDs" in error for error in errors)


def test_validate_tool_flags_malformed_on_enter(tmp_path: Path) -> None:
    world = {
        "title": "Test",
        "nodes": {
            "start": {
                "on_enter": ["bad"],
                "choices": [],
            }
        },
        "starts": [{"node": "start"}],
    }
    path = write_world(tmp_path, world)
    result = subprocess.run(
        [sys.executable, str(REPO_ROOT / "tools" / "validate.py"), str(path)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 1
    assert "on_enter effect" in result.stdout or "effect must be an object" in result.stdout


def test_list_unreachable_includes_teleports_and_missing_targets() -> None:
    world = {
        "nodes": {
            "start": {
                "on_enter": [{"type": "teleport", "target": "next"}],
                "choices": [
                    {
                        "target": "next",
                        "effects": [{"type": "teleport", "target": "missing"}],
                    }
                ],
            },
            "next": {"choices": []},
        }
    }
    graph, missing_targets = list_unreachable.build_graph(world)
    assert "next" in graph["start"]
    assert "missing" in graph["start"]
    assert any("missing node missing" in message for message in missing_targets)


def test_load_world_rejects_invalid_faction_relationships(tmp_path: Path) -> None:
    world = {
        "title": "Test",
        "nodes": {"start": {"choices": []}},
        "starts": [{"node": "start"}],
        "faction_relationships": {"Wind Choirs": {"Root Court": "rival"}},
    }
    path = write_world(tmp_path, world)
    with pytest.raises(ValueError, match="faction_relationships"):
        load_world(path)
