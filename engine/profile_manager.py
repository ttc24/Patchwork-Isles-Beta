"""Profile selection and management utilities."""

from __future__ import annotations

import inspect
import json
import os
import shutil
import string
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Awaitable, Callable, List


class ProfileError(Exception):
    """Raised when a profile cannot be created or loaded."""


PROFILE_FILENAME = "profile.json"
DEFAULT_PROFILE_ROOT = Path("profiles")
DEFAULT_SAVE_ROOT = Path("saves")
_VALID_PROFILE_CHARS = set(string.ascii_lowercase + string.digits + "-_")


@dataclass(frozen=True)
class ProfileSelection:
    name: str
    profile_path: Path
    save_root: Path


def default_profile() -> dict:
    return {
        "unlocked_starts": [],
        "legacy_tags": [],
        "seen_endings": [],
        "flags": {},
        "tick_counter": 0,
    }


def _normalize_profile(data: dict) -> dict:
    if not isinstance(data.get("unlocked_starts"), list):
        data["unlocked_starts"] = []
    if not isinstance(data.get("legacy_tags"), list):
        data["legacy_tags"] = []
    if not isinstance(data.get("seen_endings"), list):
        data["seen_endings"] = []
    if not isinstance(data.get("flags"), dict):
        data["flags"] = {}
    tick_counter = data.get("tick_counter", 0)
    if not isinstance(tick_counter, int):
        try:
            tick_counter = int(tick_counter)
        except (TypeError, ValueError):
            tick_counter = 0
    data["tick_counter"] = tick_counter
    return data


def save_profile(profile: dict, path: Path | str, *, keep_backup: bool = True) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            "w", delete=False, dir=path.parent, prefix=path.name, suffix=".tmp", encoding="utf-8"
        ) as tmp_file:
            json.dump(profile, tmp_file, indent=2)
            tmp_file.write("\n")
            tmp_path = Path(tmp_file.name)
        if keep_backup and path.exists():
            backup_path = path.with_suffix(path.suffix + ".bak")
            shutil.copy2(path, backup_path)
        os.replace(str(tmp_path), str(path))
    except OSError as exc:
        print(f"[Profile] Failed to save profile: {exc}", file=sys.stderr)
        if tmp_path is not None:
            try:
                tmp_path.unlink()
            except OSError:
                pass


def load_profile(path: Path | str) -> dict:
    path = Path(path)
    if not path.exists():
        profile = default_profile()
        save_profile(profile, path)
        return profile
    with open(path, "r", encoding="utf-8") as handle:
        data = json.load(handle)
    data.setdefault("unlocked_starts", [])
    data.setdefault("legacy_tags", [])
    data.setdefault("seen_endings", [])
    data.setdefault("flags", {})
    data.setdefault("tick_counter", 0)
    data = _normalize_profile(data)
    save_profile(data, path)
    return data


def _normalize_profile_name(name: str) -> str:
    cleaned = "".join(ch for ch in name.strip().lower() if ch in _VALID_PROFILE_CHARS)
    if not cleaned:
        raise ProfileError("Profile names must contain letters or numbers.")
    return cleaned


def _list_profiles(base_dir: Path) -> List[str]:
    if not base_dir.exists():
        return []
    profiles = []
    for child in sorted(base_dir.iterdir()):
        if not child.is_dir():
            continue
        if (child / PROFILE_FILENAME).exists():
            profiles.append(child.name)
    return profiles


async def _prompt_new_profile(
    base_dir: Path,
    save_root: Path,
    *,
    input_func: Callable[[str], str | Awaitable[str]],
    print_func: Callable[[str], None],
) -> ProfileSelection:
    while True:
        raw_name = await _resolve_input(input_func, "Enter new profile name: ")
        try:
            name = _normalize_profile_name(raw_name)
        except ProfileError as exc:
            print_func(f"[!] {exc}")
            continue
        profile_dir = base_dir / name
        if profile_dir.exists():
            print_func("[!] That profile already exists.")
            continue
        profile_dir.mkdir(parents=True, exist_ok=True)
        profile_path = profile_dir / PROFILE_FILENAME
        save_profile(default_profile(), profile_path)
        return ProfileSelection(
            name=name,
            profile_path=profile_path,
            save_root=save_root / name,
        )


async def select_profile(
    *,
    base_dir: Path | str = DEFAULT_PROFILE_ROOT,
    save_root: Path | str = DEFAULT_SAVE_ROOT,
    input_func: Callable[[str], str | Awaitable[str]] = input,
    print_func: Callable[[str], None] = print,
) -> ProfileSelection:
    base_dir = Path(base_dir)
    save_root = Path(save_root)
    base_dir.mkdir(parents=True, exist_ok=True)
    save_root.mkdir(parents=True, exist_ok=True)

    while True:
        profiles = _list_profiles(base_dir)
        if not profiles:
            print_func("No profiles found. Let's create one.")
            return await _prompt_new_profile(
                base_dir, save_root, input_func=input_func, print_func=print_func
            )

        print_func("Select a profile:")
        for idx, name in enumerate(profiles, start=1):
            print_func(f"  {idx}. {name}")
        print_func("  N. New profile")
        print_func("  Q. Quit")

        choice = (await _resolve_input(input_func, "> ")).strip().lower()
        if choice in {"q", "quit"}:
            print_func("Goodbye!")
            sys.exit(0)
        if choice in {"n", "new"}:
            return await _prompt_new_profile(
                base_dir, save_root, input_func=input_func, print_func=print_func
            )
        if choice.isdigit():
            index = int(choice)
            if 1 <= index <= len(profiles):
                name = profiles[index - 1]
                profile_path = base_dir / name / PROFILE_FILENAME
                return ProfileSelection(
                    name=name,
                    profile_path=profile_path,
                    save_root=save_root / name,
                )
        print_func("Pick a valid profile number, N for new, or Q to quit.")


async def _resolve_input(
    input_func: Callable[[str], str | Awaitable[str]],
    prompt: str,
) -> str:
    result = input_func(prompt)
    if inspect.isawaitable(result):
        return await result
    return result
