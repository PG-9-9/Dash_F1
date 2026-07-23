"""Shared data models for the headless replay server."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ReplayDataset:
    """Complete in-memory dataset required by the headless replay controller."""
    frames: list[dict[str, Any]]
    track_statuses: list[dict[str, Any]]
    race_control_messages: list[dict[str, Any]]
    total_laps: int
    driver_colors: dict[str, Any]
    session_info: dict[str, Any]
    driver_names: dict[str, str] = field(default_factory=dict)
    track_geometry: dict[str, list[float]] = field(default_factory=dict)
    lap_times: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
