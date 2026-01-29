"""Interactive options menu for the terminal engine."""

from __future__ import annotations

import inspect
from typing import Awaitable, Callable, Optional, Tuple

from .settings import SETTINGS_PATH, Settings, save_settings

MenuCallback = Callable[[Settings], None | Awaitable[None]]
InputFunc = Callable[[str], str | Awaitable[str]]
PrintFunc = Callable[[str], None]


_ENTRY_SPEC = (
    ("audio_master", "Master Volume", "volume"),
    ("audio_music", "Music Volume", "volume"),
    ("audio_sfx", "SFX Volume", "volume"),
    ("window_mode", "Window Mode", "window"),
    ("vsync", "VSync", "toggle"),
    ("ui_scale", "UI Scale", "scale"),
    ("text_speed", "Text Speed", "text_speed"),
    ("high_contrast", "High Contrast", "toggle"),
    ("reduce_animations", "Reduce Animations", "toggle"),
    ("caption_audio_cues", "Caption Audio Cues", "toggle"),
    ("doom_clock_enabled", "Doom Clock", "toggle"),
)


async def options_menu(
    current_settings: Settings,
    *,
    apply_callback: Optional[MenuCallback] = None,
    input_func: InputFunc = input,
    print_func: PrintFunc = print,
) -> Tuple[Settings, bool]:
    """Run the options UI loop and return ``(settings, changed)``."""

    working = current_settings.copy()
    selection = 0
    changed = False

    while True:
        print_func("")
        print_func("=== Options ===")
        for idx, (field, label, entry_type) in enumerate(_ENTRY_SPEC):
            prefix = ">" if idx == selection else " "
            value = _format_value(getattr(working, field), entry_type)
            print_func(f"{prefix} {label}: {value}")
        print_func(
            "Use W/S (or Up/Down) to move, A/D (Left/Right) to adjust, Enter to edit, R to reset."
        )
        print_func("Press Esc to go back without further changes.")

        raw = await _resolve_input(input_func, "Options> ")
        if raw is None:
            raw = ""
        command = raw.strip().lower()
        if command == "":
            command = "enter"

        if command in {"esc", "escape", "\x1b"}:
            break
        if command in {"w", "up", "k"}:
            selection = (selection - 1) % len(_ENTRY_SPEC)
            continue
        if command in {"s", "down", "j"}:
            selection = (selection + 1) % len(_ENTRY_SPEC)
            continue

        field, label, entry_type = _ENTRY_SPEC[selection]
        if command in {"a", "left", "h", "-"}:
            if _adjust_entry(working, field, entry_type, -1):
                changed = True
                await _apply_callback(apply_callback, working)
            continue
        if command in {"d", "right", "l", "+"}:
            if _adjust_entry(working, field, entry_type, 1):
                changed = True
                await _apply_callback(apply_callback, working)
            continue
        if command == "enter":
            if await _activate_entry(working, field, entry_type, input_func, print_func):
                changed = True
                await _apply_callback(apply_callback, working)
            continue
        if command in {"r", "reset"}:
            if _reset_entry(working, field):
                changed = True
                await _apply_callback(apply_callback, working)
            continue

        print_func("Unrecognised input. Try W/S, A/D, Enter, R, or Esc.")

    if changed:
        saved = save_settings(working)
        print_func(f"[Settings] Saved to {SETTINGS_PATH.name}.")
        return saved, True

    print_func("[Settings] No changes made.")
    return current_settings, False


async def _apply_callback(callback: Optional[MenuCallback], settings: Settings) -> None:
    if callback is None:
        return
    result = callback(settings.copy())
    if inspect.isawaitable(result):
        await result


async def _resolve_input(input_func: InputFunc, prompt: str) -> str | None:
    result = input_func(prompt)
    if inspect.isawaitable(result):
        return await result
    return result


def _format_value(value, entry_type: str) -> str:
    if entry_type == "volume":
        return f"{float(value) * 100:.0f}%"
    if entry_type == "toggle":
        return "On" if bool(value) else "Off"
    if entry_type == "window":
        return str(value).title()
    if entry_type == "scale":
        return f"{float(value):.2f}x"
    if entry_type == "text_speed":
        speed = float(value)
        return "Instant" if speed <= 0 else f"{speed:.2f}x"
    return str(value)


def _adjust_entry(settings: Settings, field: str, entry_type: str, direction: int) -> bool:
    previous = getattr(settings, field)
    if entry_type == "volume":
        step = 0.05 * direction
        setattr(settings, field, _clamp_volume(previous + step))
    elif entry_type == "scale":
        step = 0.1 * direction
        setattr(settings, field, _clamp_scale(previous + step))
    elif entry_type == "text_speed":
        step = 0.25 * direction
        setattr(settings, field, _clamp_text_speed(previous + step))
    elif entry_type in {"toggle", "window"}:
        _toggle_entry(settings, field, entry_type)
    else:
        return False
    settings.clamp()
    return getattr(settings, field) != previous


async def _activate_entry(
    settings: Settings,
    field: str,
    entry_type: str,
    input_func: InputFunc,
    print_func: PrintFunc,
) -> bool:
    if entry_type == "volume":
        prompt = "Enter volume (0-100, blank to cancel): "
        return await _prompt_float(
            settings, field, prompt, 0.0, 1.0, input_func, print_func, divisor=100.0
        )
    if entry_type == "scale":
        prompt = "Enter UI scale (0.5-2.0, blank to cancel): "
        return await _prompt_float(
            settings, field, prompt, 0.5, 2.0, input_func, print_func
        )
    if entry_type == "text_speed":
        prompt = "Enter text speed (0-3, 0 = instant, blank to cancel): "
        return await _prompt_float(
            settings, field, prompt, 0.0, 3.0, input_func, print_func
        )
    if entry_type in {"toggle", "window"}:
        before = getattr(settings, field)
        _toggle_entry(settings, field, entry_type)
        return getattr(settings, field) != before
    return False


def _reset_entry(settings: Settings, field: str) -> bool:
    default_value = getattr(Settings(), field)
    before = getattr(settings, field)
    setattr(settings, field, default_value)
    settings.clamp()
    return getattr(settings, field) != before


def _toggle_entry(settings: Settings, field: str, entry_type: str) -> None:
    if entry_type == "toggle":
        setattr(settings, field, not bool(getattr(settings, field)))
    elif entry_type == "window":
        current = str(getattr(settings, field)).lower()
        setattr(settings, field, "fullscreen" if current != "fullscreen" else "windowed")
    settings.clamp()


async def _prompt_float(
    settings: Settings,
    field: str,
    prompt: str,
    minimum: float,
    maximum: float,
    input_func: InputFunc,
    print_func: PrintFunc,
    divisor: float = 1.0,
) -> bool:
    raw = await _resolve_input(input_func, prompt)
    if raw is None:
        return False
    stripped = raw.strip()
    if not stripped:
        return False
    try:
        value = float(stripped)
    except ValueError:
        print_func("Invalid number.")
        return False

    value /= divisor
    clamped = max(minimum, min(maximum, value))
    before = getattr(settings, field)
    setattr(settings, field, clamped)
    settings.clamp()
    return getattr(settings, field) != before


def _clamp_volume(value: float) -> float:
    return max(0.0, min(1.0, float(value)))


def _clamp_scale(value: float) -> float:
    return max(0.5, min(2.0, float(value)))


def _clamp_text_speed(value: float) -> float:
    return max(0.0, min(3.0, float(value)))
