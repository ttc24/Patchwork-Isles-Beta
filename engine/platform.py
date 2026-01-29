"""Platform helpers for desktop vs web builds."""

from __future__ import annotations

import sys
from typing import Any, Optional

IS_WEB = sys.platform == "emscripten"


def get_local_storage() -> Optional[Any]:
    if not IS_WEB:
        return None
    try:
        from js import localStorage  # type: ignore
    except Exception:
        return None
    return localStorage
