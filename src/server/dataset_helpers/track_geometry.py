"""Track shape extraction helpers for replay datasets."""

from __future__ import annotations

import math
from typing import Any

from src.server.common_helpers.json_helpers import safe_float, safe_int


def sample_geometry(telemetry: Any, max_points: int = 700) -> dict[str, list[float]]:
    if telemetry is None or len(telemetry) == 0 or "X" not in telemetry or "Y" not in telemetry:
        return {"x": [], "y": []}
    count = len(telemetry)
    step = max(1, count // max_points)
    points = [
        (float(x), float(y))
        for x, y in zip(telemetry["X"].iloc[::step], telemetry["Y"].iloc[::step])
        if math.isfinite(float(x)) and math.isfinite(float(y))
    ]
    return {"x": [point[0] for point in points], "y": [point[1] for point in points]}


def derive_track_geometry(frames: list[dict[str, Any]], max_points: int = 700) -> dict[str, list[float]]:
    """Recover one complete racing lap from replay car positions."""
    driver_counts: dict[str, int] = {}
    for frame in frames[::max(1, len(frames) // 4000)]:
        for code, data in (frame.get("drivers") or {}).items():
            x = safe_float(data.get("x"), float("nan"))
            y = safe_float(data.get("y"), float("nan"))
            if math.isfinite(x) and math.isfinite(y):
                driver_counts[code] = driver_counts.get(code, 0) + 1
    if not driver_counts:
        return {"x": [], "y": []}
    reference = max(driver_counts, key=driver_counts.get)

    lap_counts: dict[int, int] = {}
    for frame in frames[::25]:
        driver = (frame.get("drivers") or {}).get(reference)
        if not driver:
            continue
        lap = safe_int(driver.get("lap"))
        if lap >= 2:
            lap_counts[lap] = lap_counts.get(lap, 0) + 1
    if not lap_counts:
        return {"x": [], "y": []}
    target_lap = max(lap_counts, key=lap_counts.get)

    points: list[tuple[float, float]] = []
    for frame in frames:
        driver = (frame.get("drivers") or {}).get(reference)
        if not driver or safe_int(driver.get("lap")) != target_lap:
            continue
        x = safe_float(driver.get("x"), float("nan"))
        y = safe_float(driver.get("y"), float("nan"))
        if not math.isfinite(x) or not math.isfinite(y):
            continue
        if not points or abs(x - points[-1][0]) + abs(y - points[-1][1]) > 0.5:
            points.append((x, y))
    if len(points) > max_points:
        step = max(1, len(points) // max_points)
        points = points[::step][:max_points]
    return {"x": [point[0] for point in points], "y": [point[1] for point in points]}
