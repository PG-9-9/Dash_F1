"""JSON and primitive conversion helpers shared by server components."""

from __future__ import annotations

import math
from typing import Any


def safe_float(value: Any, default: float = 0.0) -> float:
    try:
        result = float(value)
        return result if math.isfinite(result) else default
    except (TypeError, ValueError):
        return default


def safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(round(float(value)))
    except (TypeError, ValueError):
        return default


def hex_color(value: Any) -> str:
    if isinstance(value, str):
        return value if value.startswith("#") else f"#{value}"
    if isinstance(value, (tuple, list)) and len(value) >= 3:
        return "#{:02X}{:02X}{:02X}".format(*[max(0, min(255, int(v))) for v in value[:3]])
    return "#B0B0B0"


def json_safe(value: Any) -> Any:
    """Convert telemetry values into strict JSON-compatible primitives."""
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, dict):
        return {str(key): json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_safe(item) for item in value]
    if hasattr(value, "item"):
        try:
            return json_safe(value.item())
        except (TypeError, ValueError):
            return None
    return str(value)
