"""Reusable calculations for the Race Intelligence Workbench."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
import csv
import io
import json
import math
import random
import statistics
from pathlib import Path
from typing import Any, Iterable

from src.intelligence.battery_deployment import analyze_battery_deployment
from src.intelligence.replay_events import precompute_replay_events
from src.intelligence.strategy_flow import StrategyContext, StrategyFlowEngine
from src.lib.tyres import get_tyre_compound_str


@dataclass
class AnalysisResult:
    title: str
    summary: str
    columns: list[str]
    rows: list[list[Any]] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


def _number(value: Any, default: float = 0.0) -> float:
    try:
        result = float(value)
        return result if math.isfinite(result) else default
    except (TypeError, ValueError):
        return default


def _integer(value: Any, default: int = 0) -> int:
    try:
        return int(round(float(value)))
    except (TypeError, ValueError):
        return default


def _median(values: Iterable[float], default: float = 0.0) -> float:
    clean = [float(value) for value in values if _number(value, -1.0) > 0]
    return statistics.median(clean) if clean else default


def _compound(value: Any) -> str:
    if isinstance(value, str):
        name = value.strip().upper()
        return "INTERMEDIATE" if name in ("INTER", "I") else name
    return get_tyre_compound_str(_integer(value, -1))


def _fmt_time(seconds: float) -> str:
    if seconds <= 0:
        return "-"
    minutes, remainder = divmod(seconds, 60)
    return f"{int(minutes)}:{remainder:06.3f}"


class RaceIntelligenceEngine:
    """Accumulates replay telemetry and exposes team-oriented analyses."""

    def __init__(self):
        self.latest: dict[str, Any] = {}
        self.snapshots: list[dict[str, Any]] = []
        self.overtakes: list[dict[str, Any]] = []
        self.pit_events: list[dict[str, Any]] = []
        self.external_laps: list[dict[str, Any]] = []
        self._previous_positions: dict[str, int] = {}
        self._previous_pit: dict[str, bool] = {}
        self._last_sample_t = -10.0
        self._overtake_cooldown: dict[tuple[str, str], float] = {}
        self._seen_rc: set[tuple] = set()
        self._flow = StrategyFlowEngine()

    @property
    def drivers(self) -> list[str]:
        frame = self.latest.get("frame") or {}
        codes = set((frame.get("drivers") or {}).keys())
        codes.update((self.latest.get("lap_times") or {}).keys())
        codes.update(str(lap.get("driver", "")) for lap in self.external_laps)
        return sorted(code for code in codes if code)

    @property
    def current_lap(self) -> int:
        session = self.latest.get("session_data") or {}
        return _integer(session.get("lap"), _integer((self.latest.get("frame") or {}).get("lap"), 1))

    @property
    def total_laps(self) -> int:
        return max(self.current_lap, _integer((self.latest.get("session_data") or {}).get("total_laps"), 60))

    def update(self, payload: dict[str, Any]) -> None:
        frame = payload.get("frame")
        if not isinstance(frame, dict):
            return
        self.latest = payload
        t = _number(frame.get("t"), _number((payload.get("session_data") or {}).get("time_s")))
        drivers = frame.get("drivers") or {}
        positions = {code: _integer(data.get("position"), 99) for code, data in drivers.items()}

        history = payload.get("intelligence_events")
        if isinstance(history, dict):
            self.overtakes = list(history.get("overtakes") or [])
            self.pit_events = list(history.get("pit_events") or [])
        else:
            self._detect_overtakes(t, frame, positions)
            self._detect_pits(t, drivers)
        self._previous_positions = positions

        if t - self._last_sample_t >= 1.0 or t < self._last_sample_t:
            if t < self._last_sample_t:
                self.snapshots.clear()
            self.snapshots.append({
                "t": t,
                "lap": _integer(frame.get("lap"), self.current_lap),
                "drivers": {code: dict(data) for code, data in drivers.items()},
            })
            self.snapshots = self.snapshots[-12000:]
            self._last_sample_t = t

    def _detect_overtakes(self, t: float, frame: dict[str, Any], positions: dict[str, int]) -> None:
        if not self._previous_positions or t <= 0:
            return
        drivers = frame.get("drivers") or {}
        for attacker, new_pos in positions.items():
            old_pos = self._previous_positions.get(attacker)
            if old_pos is None or new_pos >= old_pos:
                continue
            for victim, victim_old in self._previous_positions.items():
                victim_new = positions.get(victim)
                if victim_new is None:
                    continue
                if old_pos > victim_old and new_pos < victim_new:
                    pair = tuple(sorted((attacker, victim)))
                    if t - self._overtake_cooldown.get(pair, -999.0) < 8.0:
                        continue
                    if (drivers.get(attacker) or {}).get("in_pit") or (drivers.get(victim) or {}).get("in_pit"):
                        continue
                    if self._previous_pit.get(attacker, False) or self._previous_pit.get(victim, False):
                        continue
                    self.overtakes.append({
                        "lap": _integer(frame.get("lap"), 1),
                        "time_s": t,
                        "attacker": attacker,
                        "victim": victim,
                        "position": new_pos,
                        "drs": _integer((drivers.get(attacker) or {}).get("drs")) >= 10,
                    })
                    self._overtake_cooldown[pair] = t

    def _detect_pits(self, t: float, drivers: dict[str, dict[str, Any]]) -> None:
        for code, data in drivers.items():
            in_pit = bool(data.get("in_pit"))
            previous = self._previous_pit.get(code, False)
            if in_pit and not previous:
                self.pit_events.append({
                    "driver": code,
                    "entry_t": t,
                    "exit_t": None,
                    "lap": _integer(data.get("lap"), self.current_lap),
                    "entry_position": _integer(data.get("position"), 99),
                    "exit_position": None,
                    "compound_before": _compound(data.get("tyre")),
                    "compound_after": None,
                })
            elif previous and not in_pit:
                event = next(
                    (item for item in reversed(self.pit_events) if item["driver"] == code and item["exit_t"] is None),
                    None,
                )
                if event:
                    event["exit_t"] = t
                    event["exit_position"] = _integer(data.get("position"), 99)
                    event["compound_after"] = _compound(data.get("tyre"))
            self._previous_pit[code] = in_pit

    def import_lap_data(self, path: str | Path) -> int:
        """Import OpenF1/FastF1-like lap rows from JSON or CSV."""
        source = Path(path)
        if source.suffix.lower() == ".json":
            raw = json.loads(source.read_text(encoding="utf-8"))
            if isinstance(raw, dict):
                raw = raw.get("laps", raw.get("data", []))
        elif source.suffix.lower() == ".csv":
            raw = list(csv.DictReader(io.StringIO(source.read_text(encoding="utf-8"))))
        else:
            raise ValueError("External lap data must be a .json or .csv file")
        if not isinstance(raw, list):
            raise ValueError("Expected a list of lap records")

        normalized = []
        for row in raw:
            if not isinstance(row, dict):
                continue
            driver = row.get("driver") or row.get("Driver") or row.get("driver_number") or row.get("DriverNumber")
            lap = row.get("lap") or row.get("LapNumber") or row.get("lap_number")
            lap_time = row.get("lap_duration") or row.get("LapTimeSeconds") or row.get("time_s") or row.get("LapTime")
            if isinstance(lap_time, str) and ":" in lap_time:
                mins, secs = lap_time.rsplit(":", 1)
                lap_time = _number(mins) * 60 + _number(secs)
            if not driver or _integer(lap) <= 0 or _number(lap_time) <= 0:
                continue
            normalized.append({
                "driver": str(driver),
                "lap": _integer(lap),
                "time_s": _number(lap_time),
                "compound": _compound(row.get("compound") or row.get("Compound") or "UNKNOWN"),
                "tyre_life": _integer(row.get("tyre_life") or row.get("TyreLife")),
                "session": str(row.get("session") or row.get("Session") or "PRACTICE").upper(),
                "stint": _integer(row.get("stint") or row.get("Stint"), 1),
            })
        self.external_laps = normalized
        return len(normalized)

    def strategy_analysis(self, driver: str, risk: float = 0.5) -> AnalysisResult:
        trajectories = self.strategy_trajectories(driver, risk, 8)
        rows = []
        for rank, item in enumerate(trajectories, 1):
            rows.append([
                rank,
                item.sequence,
                _fmt_time(item.expected_time_s),
                f"P{item.expected_position}",
                f"{item.position_gain:+d}",
                f"{item.risk:.0%}",
                f"{item.reward:.3f}",
            ])
        summary = "No driver telemetry available."
        if trajectories:
            best = trajectories[0]
            summary = f"Best current route targets P{best.expected_position} with {best.risk:.0%} modeled risk."
        return AnalysisResult("Race Strategy Analyzer", summary,
                              ["Rank", "Strategy", "Remaining time", "Finish", "Gain", "Risk", "Flow reward"], rows)

    def strategy_trajectories(self, driver: str, risk: float = 0.5, count: int = 10):
        data = self._driver(driver)
        baseline = self._driver_pace(driver) or self._field_pace() or 90.0
        weather = (self.latest.get("frame") or {}).get("weather") or {}
        rain_state = str(weather.get("rain_state", "DRY")).upper()
        rain_probability = 0.8 if rain_state == "RAINING" else 0.05
        status = str(self.latest.get("track_status", "1"))
        context = StrategyContext(
            current_lap=max(1, _integer(data.get("lap"), self.current_lap)),
            total_laps=self.total_laps,
            current_compound=_compound(data.get("tyre")),
            tyre_age=max(0, _integer(data.get("tyre_life"))),
            position=max(1, _integer(data.get("position"), len(self.drivers) or 20)),
            baseline_lap_s=baseline,
            pit_loss_s=self._estimated_pit_loss(),
            safety_car=status in ("4", "6", "7", "SC", "VSC"),
            rain_probability=rain_probability,
            traffic_risk=self._traffic_risk(driver),
            risk_tolerance=max(0.0, min(1.0, risk)),
        )
        return self._flow.generate(context, count=count)

    def battles_analysis(self) -> AnalysisResult:
        drivers = (self.latest.get("frame") or {}).get("drivers") or {}
        ordered = sorted(drivers.items(), key=lambda item: _integer(item[1].get("position"), 99))
        rows = []
        for (ahead, a), (behind, b) in zip(ordered, ordered[1:]):
            distance_gap = abs(_number(a.get("dist")) - _number(b.get("dist")))
            speed_ms = max(20.0, (_number(a.get("speed"), 150) + _number(b.get("speed"), 150)) / 7.2)
            gap_s = distance_gap / speed_ms
            closing = _number(b.get("speed")) - _number(a.get("speed"))
            if gap_s <= 3.5 or closing > 20:
                threat = "ATTACK" if gap_s <= 1.2 and closing > 0 else "PRESSURE" if gap_s <= 2.0 else "WATCH"
                rows.append([f"P{_integer(a.get('position'))}", ahead, behind, f"{gap_s:.2f}s", f"{closing:+.0f} km/h", threat])
        rows.sort(key=lambda row: float(str(row[3]).rstrip("s")))
        summary = f"{len(rows)} active battle groups; {len(self.overtakes)} validated position swaps detected so far."
        notes = [
            f"Lap {event['lap']}: {event['attacker']} passed {event['victim']} for P{event['position']}"
            for event in self.overtakes[-8:]
        ]
        return AnalysisResult("Overtake & Battle Detection", summary,
                              ["Position", "Ahead", "Attacker", "Estimated gap", "Closing", "State"], rows, notes)

    def undercut_analysis(self) -> AnalysisResult:
        completed = [event for event in self.pit_events if event.get("exit_t") is not None]
        rows = []
        for event in completed:
            driver = event["driver"]
            before = event["entry_position"]
            current = _integer(self._driver(driver).get("position"), event.get("exit_position") or before)
            net = before - current
            nearby = [
                other for other in completed
                if other is not event and abs(other["lap"] - event["lap"]) <= 5
            ]
            rival = min(nearby, key=lambda item: abs(item["entry_t"] - event["entry_t"]), default=None)
            duration = _number(event["exit_t"]) - _number(event["entry_t"])
            verdict = "GAIN" if net > 0 else "LOSS" if net < 0 else "HELD"
            rows.append([
                driver, event["lap"], event["compound_before"], event["compound_after"],
                f"{duration:.1f}s", rival["driver"] if rival else "-", f"{net:+d}", verdict,
            ])
        summary = f"{len(completed)} completed stops analyzed against nearby pit windows."
        return AnalysisResult("Undercut / Overcut Report", summary,
                              ["Driver", "Lap", "From", "To", "Pit phase", "Closest rival", "Net places", "Result"], rows)

    def tyre_analysis(self) -> AnalysisResult:
        groups: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
        for code, entries in (self.latest.get("lap_times") or {}).items():
            for entry in entries:
                if self._clean_lap(entry):
                    groups[(code, _compound(entry.get("tyre")))].append(entry)
        for entry in self.external_laps:
            groups[(str(entry["driver"]), str(entry["compound"]))].append(entry)

        rows = []
        for (code, compound), entries in groups.items():
            times = [_number(entry.get("time_s")) for entry in entries]
            ages = [_integer(entry.get("tyre_life"), index + 1) for index, entry in enumerate(entries)]
            slope = self._linear_slope(ages, times)
            latest = self._driver(code)
            age = _integer(latest.get("tyre_life"), max(ages, default=0))
            cliff = {"SOFT": 18, "MEDIUM": 30, "HARD": 42, "INTERMEDIATE": 30, "WET": 38}.get(compound, 30)
            health = max(0, min(100, round(100 * (1 - age / max(1, cliff + 8)))))
            confidence = "HIGH" if len(entries) >= 8 else "MEDIUM" if len(entries) >= 4 else "LOW"
            rows.append([code, compound, len(entries), _fmt_time(_median(times)), f"{slope:+.3f}s/lap", age, f"{health}%", confidence])
        rows.sort(key=lambda row: (row[0], row[1]))
        return AnalysisResult("Tyre Performance Model", f"Modeled {len(rows)} driver-compound stints with fuel-sensitive observed pace.",
                              ["Driver", "Compound", "Clean laps", "Median pace", "Degradation", "Current age", "Health", "Confidence"], rows)

    def safety_car_analysis(self) -> AnalysisResult:
        status = str(self.latest.get("track_status", "1"))
        active = status in ("4", "6", "7", "SC", "VSC")
        rows = []
        for code in self.drivers:
            data = self._driver(code)
            age = _integer(data.get("tyre_life"))
            compound = _compound(data.get("tyre"))
            normal_loss = self._estimated_pit_loss()
            effective_loss = normal_loss * (0.43 if active else 1.0)
            remaining = self.total_laps - _integer(data.get("lap"), self.current_lap)
            benefit = max(0.0, normal_loss - effective_loss) + max(0, age - 12) * 0.18
            recommendation = "PIT NOW" if active and age >= 10 and remaining >= 5 else "STAY OUT"
            if active and remaining < 5:
                recommendation = "PROTECT TRACK POSITION"
            rows.append([code, f"P{_integer(data.get('position'), 99)}", compound, age,
                         f"{effective_loss:.1f}s", f"{benefit:.1f}s", recommendation])
        phase = "ACTIVE" if active else "not active"
        return AnalysisResult("Safety Car Decision Tool", f"Neutralization is {phase}; pit-loss model uses current track status.",
                              ["Driver", "Position", "Tyre", "Age", "Effective pit loss", "Potential saving", "Call"], rows)

    def driver_comparison(self, first: str, second: str) -> AnalysisResult:
        rows = []
        for label, getter, lower_better in (
            ("Position", lambda c: _integer(self._driver(c).get("position"), 99), True),
            ("Median clean lap", lambda c: self._driver_pace(c), True),
            ("Recent average speed", self._recent_speed, False),
            ("Tyre age", lambda c: _integer(self._driver(c).get("tyre_life")), True),
            ("Overtakes", lambda c: sum(1 for e in self.overtakes if e["attacker"] == c), False),
            ("Pit stops", lambda c: sum(1 for e in self.pit_events if e["driver"] == c), True),
        ):
            a, b = getter(first), getter(second)
            if label == "Median clean lap":
                display_a, display_b = _fmt_time(_number(a)), _fmt_time(_number(b))
            elif label == "Recent average speed":
                display_a, display_b = f"{_number(a):.1f} km/h", f"{_number(b):.1f} km/h"
            else:
                display_a, display_b = str(a), str(b)
            winner = first if (a < b if lower_better else a > b) else second if a != b else "EVEN"
            rows.append([label, display_a, display_b, winner])
        pace_delta = self._driver_pace(first) - self._driver_pace(second)
        summary = f"{first} is {abs(pace_delta):.3f}s/lap {'faster' if pace_delta < 0 else 'slower'} than {second} on clean-lap median."
        return AnalysisResult("Driver Performance Comparison", summary, ["Metric", first, second, "Advantage"], rows)

    def race_control_analysis(self) -> AnalysisResult:
        rows = []
        for event in self.latest.get("race_control_events") or []:
            key = (event.get("time"), event.get("message"), event.get("racing_number"))
            self._seen_rc.add(key)
            message = str(event.get("message", ""))
            category = str(event.get("category", "GENERAL"))
            severity = "CRITICAL" if any(word in message.upper() for word in ("RED FLAG", "STOP", "DISQUALIFIED")) else "ACTION" if any(word in message.upper() for word in ("PENALTY", "INVESTIGATION", "SAFETY CAR")) else "INFO"
            rows.append([_fmt_time(_number(event.get("time"))), category, event.get("flag") or "-",
                         event.get("racing_number") or "ALL", severity, message])
        rows = rows[-100:]
        actionable = sum(1 for row in rows if row[4] in ("ACTION", "CRITICAL"))
        return AnalysisResult("Race Control Intelligence", f"{len(rows)} directives received; {actionable} require team attention.",
                              ["Time", "Category", "Flag", "Car", "Priority", "Message"], rows)

    def practice_plan(self, driver: str) -> AnalysisResult:
        laps = [lap for lap in self.external_laps if not driver or str(lap["driver"]) == driver]
        if not laps:
            laps = [
                {"driver": driver, "time_s": entry.get("time_s"), "compound": _compound(entry.get("tyre")), "tyre_life": entry.get("tyre_life", 0)}
                for entry in (self.latest.get("lap_times") or {}).get(driver, []) if self._clean_lap(entry)
            ]
        baseline = _median((lap.get("time_s") for lap in laps), self._field_pace() or 90.0)
        compounds = {str(lap.get("compound", "UNKNOWN")) for lap in laps if lap.get("compound") != "UNKNOWN"}
        run_specs = [
            ("Installation & systems", "HARD" if "HARD" in compounds else "MEDIUM", 4, "Aero correlation, brakes, radio checks"),
            ("Qualifying simulation", "SOFT", 7, "Two push laps with cooldown and setup delta"),
            ("High-fuel race run", "MEDIUM", 14, "Degradation, balance migration, lift-and-coast"),
            ("Alternative long run", "HARD", 12, "Strategy crossover and traffic sensitivity"),
            ("Start / pit practice", "SOFT", 5, "Launch, pit entry, live stop, out-lap warm-up"),
        ]
        rows = []
        elapsed = 0.0
        for number, (objective, compound, lap_count, detail) in enumerate(run_specs, 1):
            duration = lap_count * baseline + (180 if number > 1 else 120)
            rows.append([number, objective, compound, lap_count, f"{duration / 60:.0f} min", f"{lap_count * 1.65:.0f} kg + reserve", detail])
            elapsed += duration
        source = "imported practice data" if self.external_laps else "current-session pace proxy"
        return AnalysisResult("Practice Session Run Planner", f"{elapsed / 60:.0f}-minute run plan generated from {source} for {driver}.",
                              ["Run", "Objective", "Tyre", "Laps", "Block", "Fuel target", "Measurements"], rows,
                              ["Import OpenF1/FastF1 CSV or JSON lap records to replace the race-pace proxy."])

    def predictive_analysis(self) -> AnalysisResult:
        codes = self.drivers
        if not codes:
            return AnalysisResult("Predictive Replay Mode", "Waiting for driver data.", [], [])
        rng = random.Random(1701 + self.current_lap)
        finish_counts: dict[str, list[int]] = {code: [] for code in codes}
        remaining = max(1, self.total_laps - self.current_lap)
        for _ in range(400):
            scores = []
            for code in codes:
                data = self._driver(code)
                position = _integer(data.get("position"), 99)
                pace = self._driver_pace(code) or self._field_pace() or 90.0
                tyre_age = _integer(data.get("tyre_life"))
                pit_exposure = 0.0 if remaining < 8 else rng.random() * self._estimated_pit_loss() * (0.35 if tyre_age < 12 else 0.8)
                uncertainty = rng.gauss(0, 0.28 + remaining / max(25, self.total_laps) * 0.55)
                score = position * 5.2 + pace * remaining + pit_exposure + uncertainty * remaining
                scores.append((score, code))
            for finish, (_, code) in enumerate(sorted(scores), 1):
                finish_counts[code].append(finish)
        rows = []
        for code, finishes in finish_counts.items():
            expected = statistics.mean(finishes)
            win = sum(value == 1 for value in finishes) / len(finishes)
            podium = sum(value <= 3 for value in finishes) / len(finishes)
            points = sum(value <= 10 for value in finishes) / len(finishes)
            rows.append([code, f"P{expected:.1f}", f"{win:.1%}", f"{podium:.1%}", f"{points:.1%}", min(finishes), max(finishes)])
        rows.sort(key=lambda row: float(str(row[1]).lstrip("P")))
        return AnalysisResult("Predictive Replay Mode", f"400 race completions simulated from lap {self.current_lap}/{self.total_laps} with pace, tyres, and pit exposure.",
                              ["Driver", "Expected finish", "Win", "Podium", "Points", "Best", "Worst"], rows)

    def battery_analysis(self) -> tuple[AnalysisResult, ...]:
        bundle = analyze_battery_deployment(self.snapshots, self.latest, self.drivers)
        driver_result = AnalysisResult(
            "2026 Battery Deployment Model",
            bundle.summary,
            [
                "Driver", "Position", "Lap", "Harvest MJ", "Deploy MJ", "Net MJ",
                "Balance", "Peak deploy", "Peak harvest", "Risk", "Call",
            ],
            bundle.driver_rows,
            [
                "Public telemetry does not expose true state-of-charge; values are inferred from speed delta, throttle, brake and DRS.",
                "Model is scaled to 2026-style 350 kW MGU-K deployment/recovery pressure.",
            ],
        )
        zone_result = AnalysisResult(
            "Deployment Zone Finder",
            "Highest-value inferred deploy and harvest zones from the current replay window.",
            ["Driver", "Lap", "Track zone", "Phase", "Energy", "Avg speed", "Engineering use"],
            bundle.zone_rows,
        )
        policy_result = AnalysisResult(
            "RL/ECMS Energy Action Policy",
            "One-step action scores from public telemetry; suitable as the visible layer before training a full race simulator policy.",
            ["Driver", "Position", "Action", "Score", "Attack", "Defense", "Gap ahead", "Gap behind", "Reason"],
            bundle.policy_rows,
            [
                "SPEND/HOLD/HARVEST scores are RL-style action values using battle pressure, straight value, and inferred energy balance.",
                "A full trained RL agent needs a simulator because public feeds do not include true battery state-of-charge or team engine maps.",
            ],
        )
        soc_result = AnalysisResult(
            "SOC Proxy and Overtake Readiness",
            "Bounded reserve estimate from inferred harvest/deploy balance and current battle pressure.",
            ["Driver", "Position", "SOC proxy", "Reserve delta", "Readiness", "Confidence", "Priority", "Pressure"],
            bundle.soc_rows,
            [
                "SOC proxy is relative, not true ECU state-of-charge.",
                "Readiness combines estimated reserve with attack/defense opportunity.",
            ],
        )
        lift_result = AnalysisResult(
            "Lift-and-Coast Recovery Tradeoff",
            "Candidate lift/coast zones ranked by inferred energy recovered per second lost.",
            ["Driver", "Lap", "Track zone", "Recover", "Time cost", "Efficiency", "Use"],
            bundle.lift_coast_rows,
        )
        simulator_result = AnalysisResult(
            "Race Simulator Energy Policy",
            "Short-horizon simulator value for the chosen energy action using battle pressure and reserve proxy.",
            ["Driver", "Policy", "Projected value", "SOC proxy", "Score", "Why"],
            bundle.simulator_rows,
            [
                "This is the deployable precursor to a trained RL model: deterministic simulator now, trainable environment later.",
                "Public data supports policy scoring, but true RL optimality needs repeated historical/simulated rollouts.",
            ],
        )
        environment_result = AnalysisResult(
            "Trainable RL Environment Comparison",
            "Offline rollout comparison on the replay-derived energy environment using the current telemetry window.",
            ["Driver", "Best policy", "Best reward", "RL vs hold", "Final SOC", "RL action mix"],
            bundle.rl_environment_rows,
            [
                "Environment exposes normalized state vectors for training: track position, position, speed, controls, SOC proxy and battle pressure.",
                "Baselines are included so reward values have context, not just raw model output.",
            ],
        )
        return driver_result, zone_result, policy_result, soc_result, lift_result, simulator_result, environment_result

    def summary_report(self) -> AnalysisResult:
        frame = self.latest.get("frame") or {}
        ordered = sorted((frame.get("drivers") or {}).items(), key=lambda item: _integer(item[1].get("position"), 99))
        fastest = min(((self._driver_pace(code), code) for code in self.drivers if self._driver_pace(code) > 0), default=(0, "-"))
        best_mover = max(
            ((sum(1 for event in self.overtakes if event["attacker"] == code), code) for code in self.drivers),
            default=(0, "-"),
        )
        rows = [
            ["Session", (self.latest.get("session_data") or {}).get("event_name", "Current replay")],
            ["Progress", f"Lap {self.current_lap} of {self.total_laps}"],
            ["Leader", ordered[0][0] if ordered else "-"],
            ["Fastest clean median", f"{fastest[1]} ({_fmt_time(fastest[0])})"],
            ["Most overtakes", f"{best_mover[1]} ({best_mover[0]})"],
            ["Pit stops observed", len(self.pit_events)],
            ["Race-control messages", len(self.latest.get("race_control_events") or [])],
            ["Track status", self.latest.get("track_status", "GREEN")],
        ]
        notes = []
        for event in self.overtakes[-5:]:
            notes.append(f"Lap {event['lap']}: {event['attacker']} overtook {event['victim']} for P{event['position']}")
        for event in (self.latest.get("race_control_events") or [])[-5:]:
            notes.append(f"Race Control: {event.get('message', '')}")
        return AnalysisResult("Race Summary Report", "Live, exportable decision summary assembled from every intelligence model.",
                              ["Metric", "Value"], rows, notes)

    def report_text(self, first: str = "", second: str = "") -> str:
        sections = [
            self.summary_report(), self.battles_analysis(), self.undercut_analysis(),
            self.tyre_analysis(), self.safety_car_analysis(), self.predictive_analysis(),
        ]
        if first and second:
            sections.insert(3, self.driver_comparison(first, second))
        lines = ["F1 RACE INTELLIGENCE REPORT", "=" * 32, ""]
        for result in sections:
            lines.extend([result.title.upper(), result.summary])
            lines.extend(" | ".join(str(value) for value in row) for row in result.rows)
            lines.extend(result.notes)
            lines.append("")
        return "\n".join(lines)

    def _driver(self, code: str) -> dict[str, Any]:
        return (((self.latest.get("frame") or {}).get("drivers") or {}).get(code) or {})

    def _lap_entries(self, code: str) -> list[dict[str, Any]]:
        return list((self.latest.get("lap_times") or {}).get(code, []))

    def _driver_pace(self, code: str) -> float:
        return _median(entry.get("time_s") for entry in self._lap_entries(code) if self._clean_lap(entry))

    def _field_pace(self) -> float:
        return _median(self._driver_pace(code) for code in self.drivers)

    @staticmethod
    def _clean_lap(entry: dict[str, Any]) -> bool:
        return (
            _number(entry.get("time_s")) > 0
            and not entry.get("is_pit")
            and not entry.get("is_pit_affected")
            and not entry.get("is_out_lap")
            and not entry.get("is_outlier")
        )

    def _recent_speed(self, code: str) -> float:
        speeds = [
            _number((snapshot.get("drivers") or {}).get(code, {}).get("speed"))
            for snapshot in self.snapshots[-60:]
        ]
        return statistics.mean([speed for speed in speeds if speed > 0]) if any(speed > 0 for speed in speeds) else _number(self._driver(code).get("speed"))

    def _estimated_pit_loss(self) -> float:
        durations = [event["exit_t"] - event["entry_t"] for event in self.pit_events if event.get("exit_t")]
        return max(12.0, min(35.0, _median(durations, 22.0)))

    def _traffic_risk(self, code: str) -> float:
        data = self._driver(code)
        drivers = (self.latest.get("frame") or {}).get("drivers") or {}
        close = 0
        for other, other_data in drivers.items():
            if other == code:
                continue
            if abs(_number(data.get("dist")) - _number(other_data.get("dist"))) < 250:
                close += 1
        return min(1.0, close / 4.0)

    @staticmethod
    def _linear_slope(xs: list[int], ys: list[float]) -> float:
        pairs = [(float(x), float(y)) for x, y in zip(xs, ys) if x >= 0 and y > 0]
        if len(pairs) < 2:
            return 0.0
        x_mean = statistics.mean(x for x, _ in pairs)
        y_mean = statistics.mean(y for _, y in pairs)
        denominator = sum((x - x_mean) ** 2 for x, _ in pairs)
        return sum((x - x_mean) * (y - y_mean) for x, y in pairs) / denominator if denominator else 0.0
