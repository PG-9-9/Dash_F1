"""Headless replay state and dashboard data adapter."""

from __future__ import annotations

from datetime import datetime
import threading
from typing import Any

from src.intelligence.race_intelligence import (
    AnalysisResult,
    RaceIntelligenceEngine,
    precompute_replay_events,
)
from src.server.common_helpers.json_helpers import hex_color, json_safe, safe_float, safe_int
from src.server.dataset_helpers.track_geometry import derive_track_geometry
from src.server.dataset_loader import load_fastf1_dataset
from src.server.models import ReplayDataset


PLAYBACK_SPEEDS = (0.1, 0.25, 0.5, 1.0, 2.0, 4.0, 8.0, 16.0, 32.0, 64.0)
FPS = 25


def serialize_result(result: AnalysisResult) -> dict[str, Any]:
    """Convert an AnalysisResult dataclass into the API response shape."""
    return {
        "title": result.title,
        "summary": result.summary,
        "columns": result.columns,
        "rows": result.rows,
        "notes": result.notes,
    }


class HeadlessReplayController:
    """Thread-safe server-owned replay and intelligence state."""

    def __init__(self):
        """Initialize replay state, caches, and intelligence engines behind a lock."""
        self._lock = threading.RLock()
        self.dataset: ReplayDataset | None = None
        self.intelligence = RaceIntelligenceEngine()
        self.intelligence_events: dict[str, list[dict[str, Any]]] = {"overtakes": [], "pit_events": []}
        self.position_history: dict[str, list[dict[str, Any]]] = {}
        self.frame_index = 0.0
        self.playback_speed = 1.0
        self.paused = True
        self.loading = False
        self.loading_progress = 0.0
        self.loading_message = ""
        self.error: str | None = None
        self._analysis_cache: dict[str, Any] | None = None
        self._analysis_cache_key: tuple[Any, ...] | None = None
        self.revision = 0

    @property
    def loaded(self) -> bool:
        """Report whether a replay dataset with frames is available."""
        return self.dataset is not None and bool(self.dataset.frames)

    def set_loading(self) -> None:
        """Reset state for a new background session load."""
        with self._lock:
            self.loading = True
            self.loading_progress = 0.02
            self.loading_message = "Preparing telemetry"
            self.error = None

    def set_loading_progress(self, progress: float, message: str | None = None) -> None:
        """Update bounded loading percentage and optional status message."""
        with self._lock:
            self.loading_progress = max(0.0, min(1.0, progress))
            if message:
                self.loading_message = message

    def set_error(self, message: str) -> None:
        """Publish a failed session-load state and retain the error message."""
        with self._lock:
            self.loading = False
            self.loading_progress = 0.0
            self.loading_message = message
            self.error = message

    def set_dataset(self, dataset: ReplayDataset, autoplay: bool = True) -> None:
        """Install a prepared dataset and reset replay, history, and analysis caches."""
        if not dataset.frames:
            raise ValueError("Replay dataset contains no frames")
        with self._lock:
            self.dataset = dataset
            self.intelligence = RaceIntelligenceEngine()
            self.intelligence_events = precompute_replay_events(dataset.frames)
            self.position_history = self._precompute_position_history(dataset.frames)
            self.frame_index = 0.0
            self.playback_speed = 1.0
            self.paused = not autoplay
            self.loading = False
            self.loading_progress = 0.0
            self.loading_message = ""
            self.error = None
            self._analysis_cache = None
            self._analysis_cache_key = None
            self.revision += 1

    @staticmethod
    def _precompute_position_history(frames: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
        """Sample replay frames into stable per-driver position-history points."""
        history: dict[str, list[dict[str, Any]]] = {}
        previous_positions: dict[str, int] = {}
        sample_step = FPS * 5
        for frame_index, frame in enumerate(frames):
            drivers = frame.get("drivers") or {}
            changed = any(
                safe_int(data.get("position"), 99) != previous_positions.get(code)
                for code, data in drivers.items()
            )
            if frame_index % sample_step != 0 and not changed:
                continue
            for code, data in drivers.items():
                position = safe_int(data.get("position"), 99)
                lap = safe_int(data.get("lap"), safe_int(frame.get("lap"), 1))
                relative = safe_float(data.get("rel_dist"), 0.0)
                points = history.setdefault(code, [])
                point = {
                    "frame_index": frame_index,
                    "x": round(lap + max(0.0, min(1.0, relative)), 4),
                    "y": position,
                }
                if not points or points[-1]["x"] != point["x"] or points[-1]["y"] != position:
                    points.append(point)
            previous_positions = {
                code: safe_int(data.get("position"), 99)
                for code, data in drivers.items()
            }
        return history

    def advance(self, elapsed_s: float) -> None:
        """Move the replay cursor according to elapsed wall time and playback speed."""
        with self._lock:
            if not self.loaded or self.paused:
                return
            assert self.dataset is not None
            self.frame_index += max(0.0, elapsed_s) * FPS * self.playback_speed
            if self.frame_index >= len(self.dataset.frames) - 1:
                self.frame_index = float(len(self.dataset.frames) - 1)
                self.paused = True

    def control(self, action: str, value: Any = None) -> dict[str, Any]:
        """Apply validated playback control commands and invalidate analysis cache."""
        with self._lock:
            if not self.loaded:
                raise RuntimeError("No replay session is loaded")
            assert self.dataset is not None
            if action == "play":
                self.paused = False
            elif action == "pause":
                self.paused = True
            elif action == "toggle":
                self.paused = not self.paused
            elif action == "restart":
                self.frame_index = 0.0
                self.paused = True
            elif action == "speed":
                speed = safe_float(value, 1.0)
                self.playback_speed = min(PLAYBACK_SPEEDS, key=lambda option: abs(option - speed))
            elif action == "seek":
                progress = max(0.0, min(1.0, safe_float(value)))
                self.frame_index = progress * (len(self.dataset.frames) - 1)
            elif action == "step":
                seconds = safe_float(value)
                self.frame_index = max(0.0, min(len(self.dataset.frames) - 1, self.frame_index + seconds * FPS))
            else:
                raise ValueError(f"Unsupported replay action: {action}")
            self._analysis_cache_key = None
            return self.core_state()

    def _frame(self) -> dict[str, Any]:
        """Return the current replay frame from the cursor index."""
        assert self.dataset is not None
        index = min(int(self.frame_index), len(self.dataset.frames) - 1)
        return self.dataset.frames[index]

    def _track_status(self, t: float) -> str:
        """Resolve the active track-status code at a replay timestamp."""
        assert self.dataset is not None
        current = "1"
        for status in self.dataset.track_statuses:
            if t >= safe_float(status.get("start_time")) and (
                status.get("end_time") is None or t <= safe_float(status.get("end_time"))
            ):
                current = str(status.get("status", "1"))
        return current

    def _visible_events(self, t: float) -> dict[str, list[dict[str, Any]]]:
        """Return overtakes and pit windows visible at the current replay timestamp."""
        pits = []
        for event in self.intelligence_events["pit_events"]:
            if event["entry_t"] > t:
                continue
            visible = dict(event)
            if visible.get("exit_t") is not None and visible["exit_t"] > t:
                visible.update(exit_t=None, exit_position=None, compound_after=None)
            pits.append(visible)
        return {
            "overtakes": [event for event in self.intelligence_events["overtakes"] if event["time_s"] <= t],
            "pit_events": pits,
        }

    def _engine_payload(self) -> dict[str, Any]:
        """Build the enriched payload consumed by RaceIntelligenceEngine."""
        assert self.dataset is not None
        frame = self._frame()
        frame_index = int(self.frame_index)
        training_start = max(0, frame_index - (FPS * 90))
        training_end = min(len(self.dataset.frames), frame_index + (FPS * 90))
        training_frames = self.dataset.frames[training_start:training_end:FPS]
        t = safe_float(frame.get("t"))
        leader = min(
            (frame.get("drivers") or {}).items(),
            key=lambda item: safe_int(item[1].get("position"), 99),
            default=("", {}),
        )[0]
        session = dict(self.dataset.session_info)
        session.update({
            "time_s": t,
            "lap": safe_int(frame.get("lap"), 1),
            "leader": leader,
            "total_laps": self.dataset.total_laps,
        })
        return {
            "frame_index": frame_index,
            "frame": frame,
            "energy_training_frames": training_frames,
            "track_status": self._track_status(t),
            "playback_speed": self.playback_speed,
            "is_paused": self.paused,
            "total_frames": len(self.dataset.frames),
            "session_data": session,
            "lap_times": self.dataset.lap_times,
            "race_control_events": [
                event for event in self.dataset.race_control_messages if safe_float(event.get("time")) <= t
            ],
            "intelligence_events": self._visible_events(t),
        }

    def core_state(self) -> dict[str, Any]:
        """Serialize current replay state, frame data, controls, and loading status."""
        with self._lock:
            if not self.loaded:
                return {
                    "ready": False,
                    "loading": self.loading,
                    "loading_progress": self.loading_progress,
                    "loading_message": self.loading_message,
                    "error": self.error,
                    "server_time": datetime.utcnow().isoformat() + "Z",
                }
            assert self.dataset is not None
            payload = self._engine_payload()
            self.intelligence.update(payload)
            frame = payload["frame"]
            drivers = []
            for code, data in sorted(
                (frame.get("drivers") or {}).items(),
                key=lambda item: safe_int(item[1].get("position"), 99),
            ):
                drivers.append({
                    "code": code,
                    "name": self.dataset.driver_names.get(code, code),
                    "color": hex_color(self.dataset.driver_colors.get(code)),
                    **data,
                })
            t = safe_float(frame.get("t"))
            return json_safe({
                "ready": True,
                "loading": self.loading,
                "loading_progress": self.loading_progress,
                "loading_message": self.loading_message,
                "error": self.error,
                "revision": self.revision,
                "frame_index": int(self.frame_index),
                "total_frames": len(self.dataset.frames),
                "progress": self.frame_index / max(1, len(self.dataset.frames) - 1),
                "paused": self.paused,
                "speed": self.playback_speed,
                "time_s": t,
                "lap": safe_int(frame.get("lap"), 1),
                "total_laps": self.dataset.total_laps,
                "track_status": payload["track_status"],
                "weather": frame.get("weather") or {},
                "drivers": drivers,
                "safety_car": frame.get("safety_car"),
                "session": self.dataset.session_info,
            })

    def bootstrap(self) -> dict[str, Any]:
        """Serialize static session metadata, driver colors, track geometry, and lap times."""
        with self._lock:
            state = self.core_state()
            if not self.loaded:
                return state
            assert self.dataset is not None
            return json_safe({
                **state,
                "track_geometry": self.dataset.track_geometry,
                "driver_colors": {code: hex_color(color) for code, color in self.dataset.driver_colors.items()},
                "driver_names": self.dataset.driver_names,
                "lap_times": self.dataset.lap_times,
                "playback_speeds": PLAYBACK_SPEEDS,
            })

    def analyses(self, primary: str = "", comparison: str = "", risk: float = 0.5) -> dict[str, Any]:
        """Run or reuse cached intelligence analyses for driver selections and replay frame."""
        with self._lock:
            if not self.loaded:
                return {}
            state = self.core_state()
            drivers = [driver["code"] for driver in state["drivers"]]
            primary = primary if primary in drivers else (drivers[0] if drivers else "")
            comparison = comparison if comparison in drivers else (drivers[1] if len(drivers) > 1 else primary)
            risk = max(0.0, min(1.0, risk))
            cache_key = (state["frame_index"] // FPS, primary, comparison, round(risk, 2))
            if cache_key == self._analysis_cache_key and self._analysis_cache is not None:
                return self._analysis_cache

            (
                battery,
                battery_zones,
                battery_policy,
                battery_soc,
                battery_lift,
                battery_simulator,
                battery_rl_environment,
            ) = self.intelligence.battery_analysis()
            bundle = {
                "battery": serialize_result(battery),
                "battery_zones": serialize_result(battery_zones),
                "battery_policy": serialize_result(battery_policy),
                "battery_soc": serialize_result(battery_soc),
                "battery_lift": serialize_result(battery_lift),
                "battery_simulator": serialize_result(battery_simulator),
                "battery_rl_environment": serialize_result(battery_rl_environment),
                "strategy": serialize_result(self.intelligence.strategy_analysis(primary, risk)),
                "battles": serialize_result(self.intelligence.battles_analysis()),
                "undercut": serialize_result(self.intelligence.undercut_analysis()),
                "tyres": serialize_result(self.intelligence.tyre_analysis()),
                "safety_car": serialize_result(self.intelligence.safety_car_analysis()),
                "comparison": serialize_result(self.intelligence.driver_comparison(primary, comparison)),
                "race_control": serialize_result(self.intelligence.race_control_analysis()),
                "prediction": serialize_result(self.intelligence.predictive_analysis()),
                "selection": {"primary": primary, "comparison": comparison, "risk": risk},
                "position_history": {
                    code: [
                        {"x": point["x"], "y": point["y"]}
                        for point in self.position_history.get(code, [])
                        if point["frame_index"] <= state["frame_index"]
                    ]
                    for code in {primary, comparison}
                    if code
                },
            }
            safe_bundle = json_safe(bundle)
            self._analysis_cache_key = cache_key
            self._analysis_cache = safe_bundle
            return safe_bundle
