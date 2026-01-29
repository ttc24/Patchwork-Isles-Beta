"""Save migration registry for Patchwork Isles."""

from __future__ import annotations

import copy
from typing import Callable, Dict


class SaveMigrationError(Exception):
    """Raised when a save cannot be migrated to the latest schema."""


Migration = Callable[[Dict], Dict]


def _migrate_v0_to_v1(payload: Dict) -> Dict:
    state = payload.get("state")
    if not isinstance(state, dict):
        state = {}
        for key in (
            "current_node",
            "history",
            "start_id",
            "player",
            "active_area",
            "world_seed",
        ):
            if key in payload:
                state[key] = payload.get(key)
        if not state:
            raise SaveMigrationError("Missing state block for legacy save.")

    metadata = payload.get("metadata")
    if not isinstance(metadata, dict):
        metadata = {}

    player = state.get("player")
    if not isinstance(player, dict):
        player = {}

    upgraded = {
        "version": 1,
        "metadata": {
            "schema": "save_v1",
            "version": 1,
            "save_slot": metadata.get("save_slot") or payload.get("save_slot"),
            "saved_at": metadata.get("saved_at") or payload.get("saved_at"),
            "world_title": metadata.get("world_title") or payload.get("world_title"),
            "world_seed": metadata.get("world_seed", state.get("world_seed", 0)),
            "active_area": metadata.get("active_area", state.get("active_area")),
            "player_name": metadata.get("player_name", player.get("name")),
        },
        "state": state,
    }
    return upgraded


def _migrate_v1_to_v2(payload: Dict) -> Dict:
    metadata = payload.get("metadata")
    if not isinstance(metadata, dict):
        metadata = {}
    metadata = dict(metadata)
    metadata["schema"] = "save_v2"
    metadata["version"] = 2
    metadata.setdefault("world_signature", None)
    upgraded = dict(payload)
    upgraded["version"] = 2
    upgraded["metadata"] = metadata
    return upgraded


MIGRATIONS: Dict[int, Migration] = {
    0: _migrate_v0_to_v1,
    1: _migrate_v1_to_v2,
}


def migrate_save_payload(payload: Dict, target_version: int) -> Dict:
    if not isinstance(payload, dict):
        raise SaveMigrationError("Save payload was not an object.")

    version = payload.get("version", 0)
    if version is None:
        version = 0
    if not isinstance(version, int):
        raise SaveMigrationError("Save version missing or invalid.")
    if version > target_version:
        raise SaveMigrationError(
            f"Save schema {version} is newer than supported {target_version}."
        )

    current = copy.deepcopy(payload)
    while version < target_version:
        migrator = MIGRATIONS.get(version)
        if migrator is None:
            raise SaveMigrationError(
                f"No migration available for save schema {version}."
            )
        current = migrator(current)
        version = current.get("version", version + 1)
        if not isinstance(version, int):
            raise SaveMigrationError("Migration produced an invalid schema version.")

    return current
