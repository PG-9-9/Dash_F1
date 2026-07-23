"""Replay event precomputation for intelligence analyses."""

from __future__ import annotations

from typing import Any


def _number(value: Any, default: float = 0.0) -> float:
    try:
        result = float(value)
        return result if result == result and result not in (float("inf"), float("-inf")) else default
    except (TypeError, ValueError):
        return default


def _integer(value: Any, default: int = 0) -> int:
    try:
        return int(round(float(value)))
    except (TypeError, ValueError):
        return default


def _compound(value: Any) -> str:
    names = ["SOFT", "MEDIUM", "HARD", "INTERMEDIATE", "WET"]
    if isinstance(value, str):
        name = value.strip().upper()
        return "INTERMEDIATE" if name in ("INTER", "I") else name
    index = _integer(value, -1)
    return names[index] if 0 <= index < len(names) else "UNKNOWN"

def precompute_replay_events(frames: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    """Build deterministic pass and pit history from all replay frames."""
    overtakes: list[dict[str, Any]] = []
    pit_events: list[dict[str, Any]] = []
    previous_positions: dict[str, int] = {}
    previous_pit: dict[str, bool] = {}
    cooldown: dict[tuple[str, str], float] = {}

    for frame in frames:
        t = _number(frame.get("t"))
        drivers = frame.get("drivers") or {}
        positions = {code: _integer(data.get("position"), 99) for code, data in drivers.items()}

        for attacker, new_pos in positions.items():
            old_pos = previous_positions.get(attacker)
            if old_pos is None or new_pos >= old_pos:
                continue
            for victim, victim_old in previous_positions.items():
                victim_new = positions.get(victim)
                if victim_new is None or not (old_pos > victim_old and new_pos < victim_new):
                    continue
                pair = tuple(sorted((attacker, victim)))
                if t - cooldown.get(pair, -999.0) < 8.0:
                    continue
                if any(
                    bool((drivers.get(code) or {}).get("in_pit")) or previous_pit.get(code, False)
                    for code in (attacker, victim)
                ):
                    continue
                overtakes.append({
                    "lap": _integer(frame.get("lap"), 1),
                    "time_s": t,
                    "attacker": attacker,
                    "victim": victim,
                    "position": new_pos,
                    "drs": _integer((drivers.get(attacker) or {}).get("drs")) >= 10,
                })
                cooldown[pair] = t

        for code, data in drivers.items():
            in_pit = bool(data.get("in_pit"))
            previous = previous_pit.get(code, False)
            if in_pit and not previous:
                pit_events.append({
                    "driver": code,
                    "entry_t": t,
                    "exit_t": None,
                    "lap": _integer(data.get("lap"), _integer(frame.get("lap"), 1)),
                    "entry_position": _integer(data.get("position"), 99),
                    "exit_position": None,
                    "compound_before": _compound(data.get("tyre")),
                    "compound_after": None,
                })
            elif previous and not in_pit:
                event = next(
                    (item for item in reversed(pit_events) if item["driver"] == code and item["exit_t"] is None),
                    None,
                )
                if event:
                    event["exit_t"] = t
                    event["exit_position"] = _integer(data.get("position"), 99)
                    event["compound_after"] = _compound(data.get("tyre"))
            previous_pit[code] = in_pit
        previous_positions = positions

    return {"overtakes": overtakes, "pit_events": pit_events}
