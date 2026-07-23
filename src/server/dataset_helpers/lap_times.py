"""Lap-time conversion helpers for FastF1 sessions."""

from __future__ import annotations

from typing import Any

from src.lib.tyres import get_tyre_compound_int
from src.server.common_helpers.json_helpers import safe_float, safe_int


def build_lap_times(session: Any) -> dict[str, list[dict[str, Any]]]:
    """Convert FastF1 lap rows into the intelligence engine's portable schema."""
    result: dict[str, list[dict[str, Any]]] = {}
    if session is None or not hasattr(session, "laps"):
        return result

    for _, row in session.laps.iterrows():
        code = row.get("Driver")
        lap_number = row.get("LapNumber")
        if not code or lap_number is None:
            continue
        try:
            lap = int(lap_number)
        except (TypeError, ValueError):
            continue

        lap_time = row.get("LapTime")
        time_s = safe_float(lap_time.total_seconds(), -1.0) if hasattr(lap_time, "total_seconds") else -1.0
        tyre = get_tyre_compound_int(str(row.get("Compound", "")))
        pit_in = row.get("PitInTime")
        pit_out = row.get("PitOutTime")
        is_pit = hasattr(pit_in, "total_seconds") and not str(pit_in).startswith("NaT")
        is_out_lap = hasattr(pit_out, "total_seconds") and not str(pit_out).startswith("NaT")
        result.setdefault(str(code), []).append({
            "lap": lap,
            "time_s": float(time_s),
            "tyre": tyre,
            "tyre_life": safe_int(row.get("TyreLife")),
            "is_pit_entry": is_pit,
            "is_pit_affected": is_pit,
            "is_pit": is_pit,
            "is_out_lap": is_out_lap,
            "is_outlier": False,
            "source": "official",
        })
    for entries in result.values():
        entries.sort(key=lambda entry: entry["lap"])
    return result
