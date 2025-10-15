"""Settings persistence for Patchwork Isles."""

from __future__ import annotations

import json
import os
import sys
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict

_BASE_DIR = Path(__file__).resolve().parent.parent
SETTINGS_PATH = _BASE_DIR / "settings.json"


def _clamp(value: float, minimum: float, maximum: float) -> float:
    return max(minimum, min(maximum, value))


@dataclass
class Settings:
    """Runtime configuration toggles that persist between sessions."""

    audio_master: float = 1.0
    audio_music: float = 1.0
    audio_sfx: float = 1.0
    window_mode: str = "windowed"
    vsync: bool = True
    ui_scale: float = 1.0

    _WINDOW_MODES = {"windowed", "fullscreen"}

    def clamp(self) -> "Settings":
        self.audio_master = _clamp(float(self.audio_master), 0.0, 1.0)
        self.audio_music = _clamp(float(self.audio_music), 0.0, 1.0)
        self.audio_sfx = _clamp(float(self.audio_sfx), 0.0, 1.0)

        mode = str(self.window_mode).lower()
        if mode not in self._WINDOW_MODES:
            mode = "windowed"
        self.window_mode = mode

        self.vsync = bool(self.vsync)
        self.ui_scale = _clamp(float(self.ui_scale), 0.5, 2.0)
        return self

    def copy(self) -> "Settings":
        return Settings.from_dict(self.to_dict())

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any] | None) -> "Settings":
        if not isinstance(data, dict):
            return cls()

        def _as_float(key: str, default: float) -> float:
            try:
                return float(data.get(key, default))
            except (TypeError, ValueError):
                return default

        def _as_bool(key: str, default: bool) -> bool:
            value = data.get(key, default)
            if isinstance(value, bool):
                return value
            if isinstance(value, str):
                lowered = value.strip().lower()
                if lowered in {"true", "1", "yes", "on"}:
                    return True
                if lowered in {"false", "0", "no", "off"}:
                    return False
            return bool(value) if value is not None else default

        settings = cls(
            audio_master=_as_float("audio_master", 1.0),
            audio_music=_as_float("audio_music", 1.0),
            audio_sfx=_as_float("audio_sfx", 1.0),
            window_mode=str(data.get("window_mode", "windowed")),
            vsync=_as_bool("vsync", True),
            ui_scale=_as_float("ui_scale", 1.0),
        )
        return settings.clamp()


def load_settings(path: Path | str = SETTINGS_PATH) -> Settings:
    path = Path(path)
    try:
        with path.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
    except FileNotFoundError:
        return Settings()
    except (OSError, json.JSONDecodeError, TypeError):
        return Settings()
    return Settings.from_dict(data)


def save_settings(settings: Settings, path: Path | str = SETTINGS_PATH) -> Settings:
    path = Path(path)
    sanitized = settings.copy().clamp()
    path.parent.mkdir(parents=True, exist_ok=True)

    tmp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            "w", delete=False, dir=path.parent, prefix=path.name, suffix=".tmp", encoding="utf-8"
        ) as tmp_file:
            json.dump(sanitized.to_dict(), tmp_file, indent=2)
            tmp_file.write("\n")
            tmp_path = Path(tmp_file.name)
        os.replace(str(tmp_path), str(path))
    except OSError as exc:
        print(f"[Settings] Failed to save settings: {exc}", file=sys.stderr)
        if tmp_path is not None:
            try:
                tmp_path.unlink()
            except OSError:
                pass
    return sanitized

