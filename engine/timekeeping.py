"""Timekeeping utilities for Patchwork Isles."""

from __future__ import annotations

from typing import Mapping

ACTION_TICK_COSTS: Mapping[str, int] = {
    "move": 4,
    "explore": 1,
    "rest": 8,
}

CYCLE_LENGTH = 24
DOOM_TICK_THRESHOLD = 500


def normalize_tick_counter(value: object) -> int:
    try:
        tick = int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return 0
    return max(tick, 0)


def increment_ticks(current_ticks: int, action_type: str) -> int:
    cost = ACTION_TICK_COSTS.get(action_type, 0)
    if cost <= 0:
        return normalize_tick_counter(current_ticks)
    return normalize_tick_counter(current_ticks) + cost


def cycle_position(tick_counter: int, *, cycle_length: int = CYCLE_LENGTH) -> int:
    cycle_length = max(int(cycle_length), 1)
    return normalize_tick_counter(tick_counter) % cycle_length


def is_time_window(
    tick_counter: int,
    start: int,
    end: int,
    *,
    cycle_length: int = CYCLE_LENGTH,
) -> bool:
    cycle_length = max(int(cycle_length), 1)
    start = int(start) % cycle_length
    end = int(end) % cycle_length
    current = cycle_position(tick_counter, cycle_length=cycle_length)
    if start <= end:
        return start <= current <= end
    return current >= start or current <= end


def weekday_index(tick_counter: int, *, cycle_length: int = CYCLE_LENGTH, days: int = 7) -> int:
    cycle_length = max(int(cycle_length), 1)
    days = max(int(days), 1)
    return (normalize_tick_counter(tick_counter) // cycle_length) % days


def doom_reached(tick_counter: int, *, threshold: int = DOOM_TICK_THRESHOLD) -> bool:
    return normalize_tick_counter(tick_counter) > int(threshold)
