"""Trainable battery deployment environment built from public replay telemetry."""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Any, Callable

from src.intelligence.battery_deployment import _action_policy, _estimate_power, _number


ACTIONS = ("SPEND", "HOLD", "HARVEST", "LIFT")


@dataclass(frozen=True)
class EnergyState:
    """Normalized public-telemetry state used by ERS policy rollouts."""
    lap: int
    rel_dist: float
    position: int
    speed: float
    throttle: float
    brake: float
    drs: bool
    soc: float
    attack_pressure: float
    defense_pressure: float
    harvest_opportunity: float

    def vector(self) -> list[float]:
        """Return the ERS state as a bounded numeric feature vector for model training."""
        return [
            max(0.0, min(1.0, self.rel_dist)),
            max(0.0, min(1.0, self.position / 20.0)),
            max(0.0, min(1.0, self.speed / 360.0)),
            max(0.0, min(1.0, self.throttle / 100.0)),
            max(0.0, min(1.0, self.brake / 100.0)),
            1.0 if self.drs else 0.0,
            max(0.0, min(1.0, self.soc / 100.0)),
            max(0.0, min(1.0, self.attack_pressure)),
            max(0.0, min(1.0, self.defense_pressure)),
            max(0.0, min(1.0, self.harvest_opportunity)),
        ]


@dataclass(frozen=True)
class StepResult:
    """Single transition result returned by the ERS rollout environment."""
    state: EnergyState
    action: str
    reward: float
    soc: float
    done: bool


class BatteryEnergyEnvironment:
    """Small Gym-like environment for ERS policy research.

    It intentionally depends only on public telemetry-derived state. True battery
    state and engine maps are private, so this environment is suitable for policy
    comparison and offline training against a proxy, not for claiming ECU accuracy.
    """

    def __init__(self, frames: list[dict[str, Any]], driver: str, sample_step: int = 25):
        """Filter replay frames to the selected driver and initialize SOC state."""
        self.driver = driver
        self.frames = [
            frame for index, frame in enumerate(frames)
            if index % max(1, sample_step) == 0 and driver in (frame.get("drivers") or {})
        ]
        self.index = 0
        self.soc = 50.0

    @property
    def done(self) -> bool:
        """Report whether the rollout cursor has reached the final sampled frame."""
        return self.index >= max(0, len(self.frames) - 1)

    def reset(self, soc: float = 50.0) -> EnergyState:
        """Restart the environment cursor with a bounded initial SOC proxy."""
        self.index = 0
        self.soc = max(5.0, min(95.0, soc))
        return self._state()

    def step(self, action: str) -> StepResult:
        """Apply one ERS action, update SOC, and return the next reward-bearing transition."""
        action = action if action in ACTIONS else "HOLD"
        state = self._state()
        current = self._driver_at(self.index)
        previous = self._driver_at(max(0, self.index - 1))
        deploy_kw, harvest_kw, _ = _estimate_power(previous, current, 1.0)
        reward = self._reward(state, action, deploy_kw, harvest_kw)

        if action == "SPEND":
            self.soc -= max(0.6, deploy_kw / 90.0)
        elif action == "HARVEST":
            self.soc += max(0.5, harvest_kw / 110.0)
        elif action == "LIFT":
            self.soc += max(0.8, (harvest_kw + 50.0) / 95.0)
        else:
            self.soc += max(-0.25, min(0.35, (harvest_kw - deploy_kw) / 220.0))
        self.soc = max(5.0, min(95.0, self.soc))
        self.index = min(self.index + 1, max(0, len(self.frames) - 1))
        return StepResult(self._state(), action, reward, self.soc, self.done)

    def rollout(self, policy: Callable[[EnergyState], str], horizon: int = 120) -> dict[str, Any]:
        """Run a policy through the sampled replay horizon and summarize reward and actions."""
        state = self.reset()
        total_reward = 0.0
        counts = {action: 0 for action in ACTIONS}
        steps = 0
        while not self.done and steps < horizon:
            action = policy(state)
            result = self.step(action)
            total_reward += result.reward
            counts[result.action] += 1
            state = result.state
            steps += 1
        return {
            "driver": self.driver,
            "reward": total_reward,
            "steps": steps,
            "soc": self.soc,
            "actions": counts,
        }

    def _driver_at(self, index: int) -> dict[str, Any]:
        """Return selected-driver telemetry from a bounded frame index."""
        if not self.frames:
            return {}
        frame = self.frames[max(0, min(index, len(self.frames) - 1))]
        return (frame.get("drivers") or {}).get(self.driver) or {}

    def _state(self) -> EnergyState:
        """Build the current EnergyState from replay telemetry and battle-pressure heuristics."""
        if not self.frames:
            return EnergyState(1, 0.0, 99, 0.0, 0.0, 0.0, False, self.soc, 0.0, 0.0, 0.0)
        frame = self.frames[self.index]
        drivers = frame.get("drivers") or {}
        current = drivers.get(self.driver) or {}
        policy_row, policy_state = _action_policy(self.driver, current, drivers, 0.0, self.soc / 50.0, 0.0)
        _ = policy_row
        return EnergyState(
            lap=int(round(_number(current.get("lap"), _number(frame.get("lap"), 1)))),
            rel_dist=max(0.0, min(1.0, _number(current.get("rel_dist")))),
            position=int(round(_number(current.get("position"), 99))),
            speed=_number(current.get("speed")),
            throttle=_number(current.get("throttle")),
            brake=_number(current.get("brake")),
            drs=int(round(_number(current.get("drs")))) >= 10,
            soc=self.soc,
            attack_pressure=float(policy_state["attack_pressure"]),
            defense_pressure=float(policy_state["defense_pressure"]),
            harvest_opportunity=float(policy_state["harvest_value"]),
        )

    @staticmethod
    def _reward(state: EnergyState, action: str, deploy_kw: float, harvest_kw: float) -> float:
        """Compute proxy ERS reward for deployment value, reserve recovery, and pressure cost."""
        pressure = max(state.attack_pressure, state.defense_pressure)
        straight_value = max(0.0, min(1.0, (state.speed - 160.0) / 130.0)) * max(0.0, state.throttle / 100.0)
        reward = 0.0
        if action == "SPEND":
            reward += 0.75 * pressure + 0.35 * straight_value
            reward -= 0.45 if state.soc < 30 else 0.0
            reward -= max(0.0, deploy_kw - 250.0) / 700.0
        elif action == "HARVEST":
            reward += 0.55 * state.harvest_opportunity + 0.20 * max(0.0, 45.0 - state.soc) / 45.0
            reward -= 0.22 * pressure
        elif action == "LIFT":
            reward += 0.75 * state.harvest_opportunity + 0.30 * max(0.0, 40.0 - state.soc) / 40.0
            reward -= 0.32 * pressure + 0.08
        else:
            reward += 0.18 * pressure + 0.16 * max(0.0, 65.0 - state.soc) / 65.0
            reward -= 0.08 * state.harvest_opportunity
        reward += min(0.12, harvest_kw / 1800.0)
        return reward


def heuristic_energy_policy(state: EnergyState) -> str:
    """Select an interpretable ERS action from SOC, pressure, speed, and recovery opportunity."""
    pressure = max(state.attack_pressure, state.defense_pressure)
    if state.soc >= 58 and pressure >= 0.42 and state.speed > 150:
        return "SPEND"
    if state.harvest_opportunity >= 0.55 and pressure < 0.50:
        return "HARVEST"
    if state.soc < 34 and state.harvest_opportunity >= 0.25:
        return "LIFT"
    return "HOLD"


def compare_energy_policies(frames: list[dict[str, Any]], drivers: list[str]) -> list[list[Any]]:
    """Rank heuristic and baseline ERS policies for each driver on replay-derived frames."""
    rows: list[list[Any]] = []
    policies: dict[str, Callable[[EnergyState], str]] = {
        "RL heuristic": heuristic_energy_policy,
        "Spend all": lambda _state: "SPEND",
        "Harvest all": lambda _state: "HARVEST",
        "Hold": lambda _state: "HOLD",
    }
    for driver in drivers[:20]:
        results = {}
        for name, policy in policies.items():
            env = BatteryEnergyEnvironment(frames, driver)
            if not env.frames:
                continue
            results[name] = env.rollout(policy)
        if not results:
            continue
        best_name, best = max(results.items(), key=lambda item: item[1]["reward"])
        heuristic = results.get("RL heuristic", best)
        baseline = results.get("Hold", heuristic)
        rows.append([
            driver,
            best_name,
            f"{best['reward']:.2f}",
            f"{heuristic['reward'] - baseline['reward']:+.2f}",
            f"{heuristic['soc']:.0f}%",
            _format_action_mix(heuristic["actions"]),
        ])
    rows.sort(key=lambda row: float(row[2]), reverse=True)
    return rows


def _format_action_mix(actions: dict[str, int]) -> str:
    """Format rollout action counts as compact percentage labels."""
    total = max(1, sum(actions.values()))
    pieces = []
    for action in ACTIONS:
        value = actions.get(action, 0)
        if value:
            pieces.append(f"{action[:1]}{round(value / total * 100):.0f}%")
    return " ".join(pieces) if pieces else "-"
