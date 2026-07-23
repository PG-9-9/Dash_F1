"""FastF1 dataset loading for the server dashboard."""

from __future__ import annotations

from typing import Any, Callable

from src.server.dataset_helpers.lap_times import build_lap_times
from src.server.dataset_helpers.track_geometry import derive_track_geometry, sample_geometry
from src.server.models import ReplayDataset
from src.server.sessions import session_display_name


def _driver_labels(session: Any) -> dict[str, str]:
    names: dict[str, str] = {}
    for number in getattr(session, "drivers", []):
        driver = session.get_driver(number)
        code = str(driver.get("Abbreviation", ""))
        first_name = str(driver.get("FirstName", "")).strip()
        label = first_name.upper() if len(first_name) == 3 else code
        if code and label:
            names[code] = label
    return names


def load_fastf1_dataset(
    year: int,
    round_number: int,
    session_type: str = "R",
    refresh: bool = False,
    progress_callback: Callable[[float, str], None] | None = None,
) -> ReplayDataset:
    """Load a session without importing desktop UI modules."""
    import sys

    from src.f1_data import enable_cache, get_race_telemetry, load_session

    def report(progress: float, message: str) -> None:
        if progress_callback is not None:
            progress_callback(max(0.0, min(1.0, progress)), message)

    enable_cache()
    report(0.05, f"Loading {year} {session_display_name(session_type)} session")
    session = load_session(year, round_number, session_type)
    report(0.20, "Session loaded, preparing telemetry")
    added_refresh_flag = False
    if refresh and "--refresh-data" not in sys.argv:
        sys.argv.append("--refresh-data")
        added_refresh_flag = True
    try:
        telemetry = get_race_telemetry(
            session,
            session_type=session_type,
            progress_callback=lambda progress, message: report(0.20 + (progress * 0.65), message),
        )
    finally:
        if added_refresh_flag:
            sys.argv.remove("--refresh-data")
    report(0.90, "Building dashboard data")

    fastest_lap = session.laps.pick_fastest()
    track_telemetry = fastest_lap.get_telemetry() if fastest_lap is not None else None
    event_date = session.event.get("EventDate")
    if hasattr(event_date, "strftime"):
        event_date = event_date.strftime("%B %d, %Y")

    circuit_length = None
    if track_telemetry is not None and "Distance" in track_telemetry:
        circuit_length = float(track_telemetry["Distance"].max())

    geometry = sample_geometry(track_telemetry)
    if len(geometry["x"]) < 50:
        geometry = derive_track_geometry(telemetry["frames"])

    return ReplayDataset(
        frames=telemetry["frames"],
        track_statuses=telemetry.get("track_statuses", []),
        race_control_messages=telemetry.get("race_control_messages", []),
        total_laps=int(telemetry["total_laps"]),
        driver_colors=telemetry.get("driver_colors", {}),
        driver_names=_driver_labels(session),
        session_info={
            "event_name": str(session.event.get("EventName", "")),
            "circuit_name": str(session.event.get("Location", "")),
            "country": str(session.event.get("Country", "")),
            "year": year,
            "round": round_number,
            "session_type": session_display_name(session_type),
            "date": event_date or "",
            "circuit_length_m": circuit_length,
        },
        track_geometry=geometry,
        lap_times=build_lap_times(session),
    )
