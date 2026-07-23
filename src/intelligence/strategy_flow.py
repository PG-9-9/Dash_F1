"""Flow-based construction of diverse, high-reward race strategies.

This is a lightweight GFlowNet-style inference engine.  A strategy is built as
a sequence of actions, terminal strategies receive a positive reward, and the
next-action policy is proportional to estimated downstream reward.  The result
is a distribution of useful strategies instead of a single brittle optimum.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import math
import random
from typing import Iterable


COMPOUNDS = ("SOFT", "MEDIUM", "HARD", "INTERMEDIATE", "WET")

BASE_PACE = {
    "SOFT": -0.55,
    "MEDIUM": 0.0,
    "HARD": 0.45,
    "INTERMEDIATE": 5.0,
    "WET": 10.0,
}

DEGRADATION = {
    "SOFT": 0.075,
    "MEDIUM": 0.043,
    "HARD": 0.025,
    "INTERMEDIATE": 0.060,
    "WET": 0.045,
}


@dataclass(frozen=True)
class StrategyContext:
    """Live race context used to evaluate strategy-flow trajectories."""
    current_lap: int
    total_laps: int
    current_compound: str
    tyre_age: int
    position: int
    baseline_lap_s: float
    pit_loss_s: float = 22.0
    safety_car: bool = False
    rain_probability: float = 0.0
    traffic_risk: float = 0.25
    risk_tolerance: float = 0.5


@dataclass(frozen=True)
class StrategyAction:
    """One pit or pace instruction in a generated strategy sequence."""
    lap: int
    kind: str
    compound: str | None = None
    pace: str = "BALANCED"

    @property
    def label(self) -> str:
        """Render a strategy action as a dashboard-friendly instruction."""
        if self.kind == "PIT":
            return f"L{self.lap} PIT -> {self.compound}"
        return f"L{self.lap} PACE {self.pace}"


@dataclass
class StrategyTrajectory:
    """Evaluated strategy sequence with reward, risk, position, and rationale."""
    actions: list[StrategyAction]
    expected_time_s: float
    reward: float
    risk: float
    expected_position: int
    position_gain: int
    rationale: list[str] = field(default_factory=list)

    @property
    def signature(self) -> tuple:
        """Return a hashable identity for duplicate strategy trajectory removal."""
        return tuple((a.lap, a.kind, a.compound, a.pace) for a in self.actions)

    @property
    def sequence(self) -> str:
        """Join all action labels into a compact strategy string."""
        return " | ".join(action.label for action in self.actions)


class StrategyFlowEngine:
    """Sample strategy trajectories with reward-proportional forward flows."""

    def __init__(self, seed: int = 7):
        """Store the deterministic sampling seed for strategy generation."""
        self.seed = seed

    def generate(
        self,
        context: StrategyContext,
        count: int = 10,
        samples: int = 600,
    ) -> list[StrategyTrajectory]:
        """Produce diverse high-reward strategy trajectories for the current context."""
        if context.total_laps <= context.current_lap:
            return [self._evaluate(context, [])]

        rng = random.Random(self.seed + context.current_lap * 101 + context.position)
        candidates: dict[tuple, StrategyTrajectory] = {}

        # Include deterministic anchors so recommendations are stable and
        # understandable even before stochastic exploration fills the set.
        for actions in self._anchor_strategies(context):
            trajectory = self._evaluate(context, actions)
            candidates[trajectory.signature] = trajectory

        for _ in range(max(samples, count * 10)):
            actions = self._sample_trajectory(context, rng)
            trajectory = self._evaluate(context, actions)
            previous = candidates.get(trajectory.signature)
            if previous is None or trajectory.reward > previous.reward:
                candidates[trajectory.signature] = trajectory

        ranked = sorted(candidates.values(), key=lambda item: item.reward, reverse=True)
        return self._select_diverse(ranked, count)

    def _anchor_strategies(self, context: StrategyContext) -> Iterable[list[StrategyAction]]:
        """Yield deterministic baseline stop and pace plans for stable recommendations."""
        remaining = context.total_laps - context.current_lap
        windows = sorted({
            min(context.total_laps - 1, context.current_lap + max(1, remaining // 4)),
            min(context.total_laps - 1, context.current_lap + max(2, remaining // 2)),
            min(context.total_laps - 1, context.current_lap + max(3, (remaining * 2) // 3)),
        })
        yield [StrategyAction(context.current_lap, "PACE", pace="BALANCED")]
        for lap in windows:
            for compound in self._available_compounds(context):
                if compound != context.current_compound:
                    yield [StrategyAction(lap, "PIT", compound)]

        if remaining >= 16:
            first = context.current_lap + max(2, remaining // 3)
            second = context.current_lap + max(5, (remaining * 2) // 3)
            for first_compound, second_compound in (("MEDIUM", "SOFT"), ("HARD", "SOFT")):
                yield [
                    StrategyAction(first, "PIT", first_compound),
                    StrategyAction(second, "PIT", second_compound),
                ]

    def _sample_trajectory(self, context: StrategyContext, rng: random.Random) -> list[StrategyAction]:
        """Sample pit laps, compounds, and pace actions from reward-shaped priors."""
        remaining = context.total_laps - context.current_lap
        max_stops = 2 if remaining >= 15 else 1
        if remaining >= 35 and rng.random() < 0.18 + 0.25 * context.risk_tolerance:
            max_stops = 3

        stop_weights = [0.15, 0.58, 0.24, 0.03]
        if context.tyre_age > 18:
            stop_weights = [0.04, 0.62, 0.30, 0.04]
        stop_count = min(max_stops, self._weighted_index(stop_weights, rng))

        actions: list[StrategyAction] = []
        earliest = context.current_lap + 1
        latest = context.total_laps - 2
        if stop_count:
            slots = list(range(earliest, latest + 1))
            if len(slots) >= stop_count:
                # Central laps receive more flow because extreme stint lengths
                # usually have lower downstream reward.
                chosen = []
                for stop_no in range(stop_count):
                    target = context.current_lap + (stop_no + 1) * remaining / (stop_count + 1)
                    weights = [math.exp(-abs(lap - target) / max(2.0, remaining / 8.0)) for lap in slots]
                    lap = rng.choices(slots, weights=weights, k=1)[0]
                    chosen.append(lap)
                    slots = [value for value in slots if abs(value - lap) >= 5]
                    if not slots and stop_no + 1 < stop_count:
                        break

                previous = context.current_compound
                for lap in sorted(chosen):
                    available = [c for c in self._available_compounds(context) if c != previous]
                    compound_weights = [self._compound_flow(context, c, lap) for c in available]
                    compound = rng.choices(available, weights=compound_weights, k=1)[0]
                    actions.append(StrategyAction(lap, "PIT", compound))
                    previous = compound

        pace_roll = rng.random()
        if pace_roll < 0.22 * context.risk_tolerance:
            actions.append(StrategyAction(context.current_lap, "PACE", pace="PUSH"))
        elif pace_roll > 0.82:
            actions.append(StrategyAction(context.current_lap, "PACE", pace="CONSERVE"))
        else:
            actions.append(StrategyAction(context.current_lap, "PACE", pace="BALANCED"))
        return sorted(actions, key=lambda action: (action.lap, action.kind != "PACE"))

    @staticmethod
    def _weighted_index(weights: list[float], rng: random.Random) -> int:
        """Choose an index from explicit non-normalized weights."""
        return rng.choices(range(len(weights)), weights=weights, k=1)[0]

    @staticmethod
    def _available_compounds(context: StrategyContext) -> list[str]:
        """Limit candidate compounds according to the current rain probability."""
        if context.rain_probability >= 0.65:
            return ["INTERMEDIATE", "WET", "MEDIUM"]
        if context.rain_probability >= 0.25:
            return ["SOFT", "MEDIUM", "HARD", "INTERMEDIATE"]
        return ["SOFT", "MEDIUM", "HARD"]

    @staticmethod
    def _compound_flow(context: StrategyContext, compound: str, lap: int) -> float:
        """Score a compound choice by stint length, degradation, and weather fit."""
        stint_length = max(1, context.total_laps - lap)
        predicted_loss = BASE_PACE[compound] * stint_length
        predicted_loss += DEGRADATION[compound] * stint_length * (stint_length + 1) / 2
        if context.rain_probability >= 0.5 and compound in ("INTERMEDIATE", "WET"):
            predicted_loss -= 20.0 * context.rain_probability
        elif context.rain_probability < 0.2 and compound in ("INTERMEDIATE", "WET"):
            predicted_loss += 120.0
        return max(0.01, math.exp(-predicted_loss / 18.0))

    def _evaluate(self, context: StrategyContext, actions: list[StrategyAction]) -> StrategyTrajectory:
        """Convert a strategy action list into time, risk, reward, and rationale."""
        pit_by_lap = {a.lap: a for a in actions if a.kind == "PIT"}
        pace_action = next((a for a in actions if a.kind == "PACE"), None)
        pace = pace_action.pace if pace_action else "BALANCED"
        compound = context.current_compound if context.current_compound in COMPOUNDS else "MEDIUM"
        tyre_age = max(0, context.tyre_age)
        total = 0.0
        risk_points = 0.0
        traffic_penalty = 0.0
        rationale: list[str] = []

        pace_delta = {"PUSH": -0.20, "BALANCED": 0.0, "CONSERVE": 0.28}[pace]
        pace_deg = {"PUSH": 1.28, "BALANCED": 1.0, "CONSERVE": 0.78}[pace]

        for lap in range(context.current_lap + 1, context.total_laps + 1):
            if lap in pit_by_lap:
                compound = pit_by_lap[lap].compound or "MEDIUM"
                tyre_age = 0
                effective_pit_loss = context.pit_loss_s * (0.43 if context.safety_car else 1.0)
                total += effective_pit_loss
                traffic_penalty += context.traffic_risk * (1.5 + (lap % 4) * 0.45)

            tyre_age += 1
            deg = DEGRADATION.get(compound, DEGRADATION["MEDIUM"]) * tyre_age * pace_deg
            cliff_age = {"SOFT": 18, "MEDIUM": 30, "HARD": 42, "INTERMEDIATE": 30, "WET": 38}.get(compound, 30)
            cliff = max(0, tyre_age - cliff_age) ** 1.35 * 0.13
            risk_points += max(0, tyre_age - cliff_age) * 0.75

            weather_penalty = 0.0
            if context.rain_probability >= 0.5 and compound in ("SOFT", "MEDIUM", "HARD"):
                weather_penalty = 7.5 * context.rain_probability
                risk_points += 2.5 * context.rain_probability
            elif context.rain_probability < 0.25 and compound in ("INTERMEDIATE", "WET"):
                weather_penalty = 4.5 * (1.0 - context.rain_probability)
                risk_points += 1.5

            total += context.baseline_lap_s + BASE_PACE.get(compound, 0.0) + pace_delta + deg + cliff + weather_penalty

        total += traffic_penalty
        stop_count = len(pit_by_lap)
        risk = min(1.0, 0.08 + risk_points / max(10.0, context.total_laps - context.current_lap) / 2.8)
        risk += max(0.0, stop_count - 2) * 0.08
        risk = min(1.0, risk)

        remaining = max(1, context.total_laps - context.current_lap)
        reference = remaining * (context.baseline_lap_s + 0.9) + context.pit_loss_s
        time_gain = reference - total
        position_gain = max(-5, min(5, int(round(time_gain / 4.5))))
        expected_position = max(1, context.position - position_gain)
        reward = math.exp(max(-30.0, min(30.0, time_gain)) / 11.0)
        reward *= max(0.08, 1.0 - risk * (0.35 + 0.45 * (1.0 - context.risk_tolerance)))

        if context.safety_car and stop_count:
            rationale.append("Reduced pit loss under Safety Car")
        if pit_by_lap:
            first_stop = min(pit_by_lap)
            rationale.append(f"First stop window opens on lap {first_stop}")
        else:
            rationale.append("Track position retained with no further stop")
        if pace == "PUSH":
            rationale.append("Push phase trades tyre life for immediate pace")
        elif pace == "CONSERVE":
            rationale.append("Conserve phase protects the terminal stint")
        if context.rain_probability >= 0.25:
            rationale.append(f"Weather exposure included ({context.rain_probability:.0%} rain)")
        if risk >= 0.6:
            rationale.append("High tyre or weather sensitivity")

        return StrategyTrajectory(
            actions=actions,
            expected_time_s=round(total, 3),
            reward=round(reward, 6),
            risk=round(risk, 3),
            expected_position=expected_position,
            position_gain=context.position - expected_position,
            rationale=rationale,
        )

    @staticmethod
    def _select_diverse(ranked: list[StrategyTrajectory], count: int) -> list[StrategyTrajectory]:
        """Keep top trajectories while avoiding repeated action profiles."""
        selected: list[StrategyTrajectory] = []
        profiles: set[tuple] = set()
        for trajectory in ranked:
            profile = tuple(
                (action.kind, action.compound, action.pace)
                for action in trajectory.actions
            )
            if profile in profiles and len(selected) < max(3, count // 2):
                continue
            selected.append(trajectory)
            profiles.add(profile)
            if len(selected) >= count:
                break
        return selected
