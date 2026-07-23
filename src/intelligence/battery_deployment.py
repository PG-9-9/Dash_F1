"""Telemetry-derived ERS deployment analysis for the dashboard."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
import math
import statistics
from typing import Any

MAX_MGU_K_KW_2026 = 350.0
SECONDS_PER_SAMPLE_FALLBACK = 1.0


@dataclass
class BatteryAnalysisBundle:
    """Container for every battery-analysis table rendered by the dashboard charts."""
    summary: str
    driver_rows: list[list[Any]]
    zone_rows: list[list[Any]]
    policy_rows: list[list[Any]]
    soc_rows: list[list[Any]]
    lift_coast_rows: list[list[Any]]
    simulator_rows: list[list[Any]]
    rl_environment_rows: list[list[Any]]


def _number(value: Any, default: float = 0.0) -> float:
    """Convert telemetry scalars to finite floats for ERS heuristics."""
    try:
        result = float(value)
        return result if math.isfinite(result) else default
    except (TypeError, ValueError):
        return default


def _integer(value: Any, default: int = 0) -> int:
    """Round telemetry scalars to integers for lap, position, and DRS decisions."""
    try:
        return int(round(float(value)))
    except (TypeError, ValueError):
        return default


def _balance_label(net_mj: float) -> str:
    """Classify net ERS balance as deploy-heavy, harvest-heavy, or balanced."""
    if net_mj > 0.35:
        return "DEPLOYMENT HEAVY"
    if net_mj < -0.35:
        return "HARVEST HEAVY"
    return "BALANCED"


def _risk_label(balance_mj: float, harvest_mj: float, deploy_mj: float, samples: int) -> str:
    """Assign deployment risk from energy imbalance and sample confidence."""
    if samples < 8:
        return "LOW CONFIDENCE"
    if balance_mj > 1.0 and deploy_mj > harvest_mj * 1.25:
        return "HIGH"
    if balance_mj > 0.35:
        return "MEDIUM"
    return "LOW"


def _soc_proxy(harvest_mj: float, deploy_mj: float, samples: int) -> tuple[float, str]:
    """Estimate bounded battery reserve from inferred harvest and deployment totals."""
    if samples < 4:
        return 50.0, "LOW"
    # Public feeds do not expose SOC; this is a bounded race-window reserve estimate.
    reserve = 50.0 + (harvest_mj - deploy_mj) * 18.0
    reserve = max(5.0, min(95.0, reserve))
    confidence = "HIGH" if samples >= 90 else "MEDIUM" if samples >= 30 else "LOW"
    return reserve, confidence


def _deployment_call(balance_mj: float, risk: str) -> str:
    """Translate net energy risk into a pit-wall ERS recommendation."""
    if risk == "HIGH":
        return "Save exits before next attack zone"
    if balance_mj < -0.6:
        return "Available to spend on next straight"
    if risk == "MEDIUM":
        return "Prioritize defense, harvest under braking"
    return "Deployment window sustainable"


def _readiness_label(soc: float, attack_pressure: float, defense_pressure: float) -> str:
    """Label overtake-readiness from reserve proxy and battle pressure."""
    pressure = max(attack_pressure, defense_pressure)
    if soc >= 62 and pressure >= 0.45:
        return "READY"
    if soc >= 48 and pressure >= 0.30:
        return "BUILDING"
    if soc < 38:
        return "SAVE"
    return "WAIT"


def _policy_projection(action: str, soc: float, attack: float, defense: float, net_mj: float) -> tuple[float, str]:
    """Score a candidate ERS action against reserve, pressure, and energy balance."""
    pressure = max(attack, defense)
    if action == "SPEND":
        gain = 0.34 * pressure + 0.08 * max(0.0, soc - 50.0) / 50.0 - max(0.0, net_mj) * 0.05
        return gain, "short-run position defense/attack value"
    if action == "HARVEST":
        gain = -0.08 + 0.22 * max(0.0, 45.0 - soc) / 45.0 + 0.04 * max(0.0, net_mj)
        return gain, "sacrifices a little time to rebuild reserve"
    gain = 0.06 + 0.16 * pressure + 0.08 * max(0.0, 65.0 - soc) / 65.0
    return gain, "keeps enough reserve for the next decision point"


def _action_policy(
    code: str,
    current: dict[str, Any],
    drivers: dict[str, dict[str, Any]],
    net_mj: float,
    harvest_mj: float,
    deploy_mj: float,
) -> tuple[list[Any], dict[str, float | str]]:
    """Choose spend, hold, or harvest from current battle gaps and control inputs."""
    position = _integer(current.get("position"), 99)
    distance = _number(current.get("dist"))
    speed = _number(current.get("speed"))
    throttle = _number(current.get("throttle"))
    brake = _number(current.get("brake"))
    ahead_gap = 9999.0
    behind_gap = 9999.0
    for other_code, other in drivers.items():
        if other_code == code:
            continue
        other_position = _integer(other.get("position"), 99)
        gap_m = abs(distance - _number(other.get("dist")))
        if other_position == position - 1:
            ahead_gap = min(ahead_gap, gap_m)
        if other_position == position + 1:
            behind_gap = min(behind_gap, gap_m)

    attack_pressure = max(0.0, 1.0 - ahead_gap / 320.0)
    defense_pressure = max(0.0, 1.0 - behind_gap / 260.0)
    straight_value = max(0.0, min(1.0, (speed - 170.0) / 120.0)) * max(0.0, min(1.0, throttle / 100.0))
    harvest_value = max(0.0, min(1.0, brake / 70.0)) + (0.35 if throttle < 25 and speed > 120 else 0.0)
    depletion_penalty = max(0.0, net_mj) * 0.32
    reserve_credit = max(0.0, harvest_mj - deploy_mj) * 0.18

    spend_score = 100 * (0.48 * attack_pressure + 0.30 * defense_pressure + 0.22 * straight_value) - depletion_penalty * 100
    hold_score = 100 * (0.34 * defense_pressure + 0.26 * straight_value + 0.22 * reserve_credit + 0.18 * max(0.0, 1.0 - abs(net_mj)))
    harvest_score = 100 * (0.54 * harvest_value + 0.26 * depletion_penalty + 0.20 * max(0.0, 1.0 - attack_pressure))
    actions = [("SPEND", spend_score), ("HOLD", hold_score), ("HARVEST", harvest_score)]
    action, score = max(actions, key=lambda item: item[1])
    reason = {
        "SPEND": "attack/defense window is valuable",
        "HOLD": "reserve has more value than immediate deployment",
        "HARVEST": "braking/lift zone can rebuild usable charge",
    }[action]
    row = [
        code,
        f"P{position}",
        action,
        f"{max(0.0, min(100.0, score)):.0f}",
        f"{attack_pressure:.2f}",
        f"{defense_pressure:.2f}",
        f"{ahead_gap:.0f} m" if ahead_gap < 9000 else "-",
        f"{behind_gap:.0f} m" if behind_gap < 9000 else "-",
        reason,
    ]
    telemetry = {
        "action": action,
        "score": max(0.0, min(100.0, score)),
        "attack_pressure": attack_pressure,
        "defense_pressure": defense_pressure,
        "straight_value": straight_value,
        "harvest_value": harvest_value,
        "ahead_gap": ahead_gap,
        "behind_gap": behind_gap,
    }
    return row, telemetry


def _phase(deploy_kw: float, harvest_kw: float) -> str:
    """Classify a telemetry sample as deploy, harvest, or neutral from inferred power."""
    if deploy_kw >= 120:
        return "DEPLOY"
    if harvest_kw >= 100:
        return "HARVEST"
    return "NEUTRAL"


def _estimate_power(previous: dict[str, Any] | None, current: dict[str, Any], dt: float) -> tuple[float, float, float]:
    """Infer MGU-K deploy and harvest power from speed delta, throttle, brake, and DRS."""
    speed = _number(current.get("speed"))
    throttle = _number(current.get("throttle"))
    brake = _number(current.get("brake"))
    drs = _integer(current.get("drs")) >= 10
    prev_speed = _number(previous.get("speed"), speed) if previous else speed
    acceleration_kph_s = (speed - prev_speed) / max(0.2, dt)

    deploy_kw = 0.0
    if throttle >= 72 and speed >= 90 and brake <= 2:
        throttle_term = max(0.0, (throttle - 72.0) / 28.0) * 230.0
        acceleration_term = max(0.0, acceleration_kph_s) * 7.5
        drs_term = 38.0 if drs else 0.0
        deploy_kw = min(MAX_MGU_K_KW_2026, throttle_term + acceleration_term + drs_term)

    harvest_kw = 0.0
    if brake >= 2 or (throttle <= 25 and acceleration_kph_s < -0.8):
        brake_term = min(230.0, brake * 2.6)
        coast_term = 38.0 if throttle <= 20 else 0.0
        decel_term = max(0.0, -acceleration_kph_s) * 9.5
        harvest_kw = min(MAX_MGU_K_KW_2026, brake_term + coast_term + decel_term)

    return deploy_kw, harvest_kw, acceleration_kph_s


def _lift_coast_cost(speed_kph: float, harvest_kw: float, dt: float) -> tuple[float, float]:
    """Estimate recoverable energy and time loss for a short lift-and-coast action."""
    recover_mj = min(MAX_MGU_K_KW_2026, max(55.0, harvest_kw + 42.0)) * min(2.2, max(0.6, dt)) / 1000.0
    time_loss_s = 0.025 + max(0.0, speed_kph - 150.0) / 1000.0
    return recover_mj, time_loss_s


def analyze_battery_deployment(
    snapshots: list[dict[str, Any]],
    latest: dict[str, Any],
    drivers: list[str],
) -> BatteryAnalysisBundle:
    """Infer ERS deployment pressure from public telemetry channels.

    FastF1/OpenF1 style feeds do not expose true battery state-of-charge. This model
    therefore estimates deployment and harvest opportunities from speed delta,
    throttle, brake and DRS signals, then reports relative energy balance.
    """
    if not snapshots or not drivers:
        return BatteryAnalysisBundle("Waiting for enough telemetry to infer ERS behavior.", [], [], [], [], [], [], [])

    driver_rows: list[list[Any]] = []
    policy_rows: list[list[Any]] = []
    soc_rows: list[list[Any]] = []
    lift_coast_rows: list[list[Any]] = []
    simulator_rows: list[list[Any]] = []
    zone_accumulator: dict[tuple[str, int, int, str], dict[str, float]] = defaultdict(lambda: {
        "deploy_mj": 0.0,
        "harvest_mj": 0.0,
        "samples": 0.0,
        "avg_speed": 0.0,
    })
    current_frame = latest.get("frame") or {}
    current_lap = _integer(current_frame.get("lap"), _integer((latest.get("session_data") or {}).get("lap"), 1))

    for code in drivers:
        previous: dict[str, Any] | None = None
        previous_t: float | None = None
        deploy_mj = 0.0
        harvest_mj = 0.0
        sample_count = 0
        recent_deploy_kw: list[float] = []
        recent_harvest_kw: list[float] = []
        lift_candidates: list[tuple[float, float, int, int, float]] = []

        for snapshot in snapshots[-240:]:
            frame_drivers = snapshot.get("drivers") or {}
            current = frame_drivers.get(code)
            if not current:
                continue
            t = _number(snapshot.get("t"), previous_t or 0.0)
            dt = max(0.2, t - previous_t) if previous_t is not None else SECONDS_PER_SAMPLE_FALLBACK
            deploy_kw, harvest_kw, acceleration = _estimate_power(previous, current, dt)
            deploy_mj += deploy_kw * dt / 1000.0
            harvest_mj += harvest_kw * dt / 1000.0
            sample_count += 1
            recent_deploy_kw.append(deploy_kw)
            recent_harvest_kw.append(harvest_kw)

            lap = _integer(current.get("lap"), current_lap)
            rel_dist = max(0.0, min(0.999, _number(current.get("rel_dist"))))
            zone = int(rel_dist * 10)
            phase = _phase(deploy_kw, harvest_kw)
            if phase != "NEUTRAL":
                key = (code, lap, zone, phase)
                zone_accumulator[key]["deploy_mj"] += deploy_kw * dt / 1000.0
                zone_accumulator[key]["harvest_mj"] += harvest_kw * dt / 1000.0
                zone_accumulator[key]["samples"] += 1
                zone_accumulator[key]["avg_speed"] += _number(current.get("speed"))
            if _number(current.get("speed")) > 120 and _number(current.get("throttle")) < 35 and acceleration < -0.3:
                recover_mj, time_loss = _lift_coast_cost(_number(current.get("speed")), harvest_kw, dt)
                lap = _integer(current.get("lap"), current_lap)
                zone = int(max(0.0, min(0.999, _number(current.get("rel_dist")))) * 10)
                lift_candidates.append((recover_mj / max(0.02, time_loss), recover_mj, lap, zone, time_loss))

            previous = current
            previous_t = t

        net_mj = deploy_mj - harvest_mj
        risk = _risk_label(net_mj, harvest_mj, deploy_mj, sample_count)
        soc, soc_confidence = _soc_proxy(harvest_mj, deploy_mj, sample_count)
        peak_deploy = max(recent_deploy_kw, default=0.0)
        peak_harvest = max(recent_harvest_kw, default=0.0)
        current = (current_frame.get("drivers") or {}).get(code) or {}
        driver_rows.append([
            code,
            f"P{_integer(current.get('position'), 99)}",
            _integer(current.get("lap"), current_lap),
            f"{harvest_mj:.2f}",
            f"{deploy_mj:.2f}",
            f"{net_mj:+.2f}",
            _balance_label(net_mj),
            f"{peak_deploy:.0f} kW",
            f"{peak_harvest:.0f} kW",
            risk,
            _deployment_call(net_mj, risk),
        ])
        policy_row, policy_state = _action_policy(code, current, current_frame.get("drivers") or {}, net_mj, harvest_mj, deploy_mj)
        policy_rows.append(policy_row)
        readiness = _readiness_label(soc, float(policy_state["attack_pressure"]), float(policy_state["defense_pressure"]))
        soc_rows.append([
            code,
            f"P{_integer(current.get('position'), 99)}",
            f"{soc:.0f}%",
            f"{max(0.0, harvest_mj - deploy_mj):.2f} MJ",
            readiness,
            soc_confidence,
            "attack" if float(policy_state["attack_pressure"]) >= float(policy_state["defense_pressure"]) else "defense",
            f"{max(float(policy_state['attack_pressure']), float(policy_state['defense_pressure'])):.2f}",
        ])
        projection, reason = _policy_projection(str(policy_state["action"]), soc, float(policy_state["attack_pressure"]), float(policy_state["defense_pressure"]), net_mj)
        simulator_rows.append([
            code,
            str(policy_state["action"]),
            f"{projection:+.2f}s value",
            f"{soc:.0f}%",
            f"{float(policy_state['score']):.0f}",
            reason,
        ])
        for _, recover_mj, lap, zone, time_loss in sorted(lift_candidates, reverse=True)[:2]:
            lift_coast_rows.append([
                code,
                lap,
                f"{zone * 10}-{zone * 10 + 10}%",
                f"{recover_mj:.2f} MJ",
                f"{time_loss:.2f}s",
                f"{recover_mj / max(0.02, time_loss):.2f} MJ/s",
                "efficient recharge window",
            ])

    zone_rows = []
    for (code, lap, zone, phase), values in zone_accumulator.items():
        samples = max(1.0, values["samples"])
        start = zone * 10
        end = start + 10
        value_mj = values["deploy_mj"] if phase == "DEPLOY" else values["harvest_mj"]
        zone_rows.append([
            code,
            lap,
            f"{start}-{end}%",
            phase,
            f"{value_mj:.2f} MJ",
            f"{values['avg_speed'] / samples:.0f} km/h",
            "Attack/defend candidate" if phase == "DEPLOY" else "Recharge candidate",
        ])
    zone_rows.sort(key=lambda row: float(str(row[4]).split()[0]), reverse=True)

    if driver_rows:
        high_risk = sum(1 for row in driver_rows if row[9] == "HIGH")
        median_deploy = statistics.median(float(row[4]) for row in driver_rows)
        summary = (
            f"ERS proxy uses 2026-scale 350 kW MGU-K limits across the last telemetry window; "
            f"median inferred deployment is {median_deploy:.2f} MJ and {high_risk} drivers are deployment-limited."
        )
    else:
        summary = "Waiting for enough telemetry to infer ERS behavior."
    policy_rows.sort(key=lambda row: float(row[3]), reverse=True)
    soc_rows.sort(key=lambda row: float(str(row[2]).rstrip("%")), reverse=True)
    lift_coast_rows.sort(key=lambda row: float(str(row[5]).split()[0]), reverse=True)
    simulator_rows.sort(key=lambda row: float(str(row[4])), reverse=True)
    from src.intelligence.battery_rl_environment import compare_energy_policies

    training_frames = list(latest.get("energy_training_frames") or [])
    if not training_frames:
        training_frames = [
            {"lap": snapshot.get("lap"), "drivers": snapshot.get("drivers") or {}}
            for snapshot in snapshots[-900:]
        ]
    rl_environment_rows = compare_energy_policies(training_frames, drivers)
    return BatteryAnalysisBundle(
        summary,
        driver_rows,
        zone_rows[:24],
        policy_rows,
        soc_rows,
        lift_coast_rows[:24],
        simulator_rows,
        rl_environment_rows,
    )
