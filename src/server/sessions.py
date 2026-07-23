"""Session labels and FastF1 event catalog helpers for server mode."""

from __future__ import annotations

from typing import Any


SESSION_NAMES = {
    "R": "Race",
    "S": "Sprint",
    "Q": "Qualifying",
    "SQ": "Sprint Qualifying",
    "FP1": "Practice 1",
    "FP2": "Practice 2",
    "FP3": "Practice 3",
}

SUPPORTED_SESSIONS = frozenset(SESSION_NAMES)
WEEKEND_SESSIONS = {
    "conventional": ["FP1", "FP2", "FP3", "Q", "R"],
    "sprint": ["FP1", "SQ", "S", "R"],
    "sprint_shootout": ["FP1", "SQ", "S", "R"],
}


def session_display_name(session_type: str) -> str:
    return SESSION_NAMES.get(session_type.upper(), session_type)


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(round(float(value)))
    except (TypeError, ValueError):
        return default


def _json_safe(value: Any) -> Any:
    if value is None or isinstance(value, (str, bool, int, float)):
        return value
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    if hasattr(value, "item"):
        try:
            return _json_safe(value.item())
        except (TypeError, ValueError):
            return None
    return str(value)


def load_event_catalog(year: int) -> dict[str, Any]:
    """Return available sessions for each event in a championship year."""
    import fastf1

    schedule = fastf1.get_event_schedule(year, include_testing=False)
    events = []
    for _, row in schedule.iterrows():
        round_number = _safe_int(row.get("RoundNumber"))
        if round_number <= 0:
            continue
        event_format = str(row.get("EventFormat", "")).lower()
        event_date = row.get("EventDate")
        if hasattr(event_date, "strftime"):
            event_date = event_date.strftime("%Y-%m-%d")
        events.append({
            "round": round_number,
            "name": str(row.get("EventName", "")),
            "location": str(row.get("Location", "")),
            "country": str(row.get("Country", "")),
            "date": str(event_date or ""),
            "sessions": WEEKEND_SESSIONS.get(event_format, WEEKEND_SESSIONS["conventional"]),
        })
    return _json_safe({"year": year, "events": events})
