# Battery Intelligence and Algorithms

The Battery tab explores hybrid-energy management using channels available in
public telemetry. It combines physics-shaped heuristics, local action scoring,
a short-horizon value model, and a Gym-like rollout environment.

## What Is Measured and What Is Inferred

Public telemetry provides speed, throttle, brake, DRS state, position, lap, and
relative track distance. It does not provide:

- True Energy Store state-of-charge.
- MGU-K electrical or mechanical power.
- Battery voltage, current, temperature, or degradation.
- ICE torque, fuel flow, or power-split command.
- Energy deployment maps or driver mode selections.
- Team constraints and target SOC.

Every value labeled deploy, harvest, SOC, recovery, or reward is therefore a
proxy derived by this project. The tab is intended for relative comparison,
research prototyping, and explainable policy experiments.

## 2026 Regulatory Context

The model's power ceiling is `350 kW`, reflecting the major increase in 2026
MGU-K capability described by the
[FIA's 2026 technical overview](https://www.fia.com/news/new-era-competition-fia-showcases-future-focused-formula-1-regulations-2026-and-beyond).

The regulations are evolving. In April 2026, the FIA announced that 350 kW
would remain available in key acceleration/overtaking zones while deployment
would be limited to 250 kW elsewhere, alongside other energy-management
changes. See the
[FIA's April 2026 refinements](https://www.fia.com/news/refinements-2026-fia-formula-1-regulations-agreed-all-stakeholders).

The current code applies a global 350 kW cap and does not identify official FIA
key-acceleration zones. It is a 2026-scale research model, not a regulatory
compliance simulator.

## Analysis Window

The telemetry engine retains approximately one snapshot per second. Battery
aggregation uses up to the latest 240 snapshots for each driver.

For each consecutive sample:

```text
dt = max(0.2, current_time - previous_time)
acceleration = (speed_km_h_now - speed_km_h_previous) / dt
```

The acceleration unit remains km/h per second because coefficients were tuned
against those public channels.

## Inferred Deployment Power

Deployment is considered possible when:

```text
throttle >= 72%
speed >= 90 km/h
brake <= 2
```

Power terms:

```text
throttle_term = max(0, (throttle - 72) / 28) * 230
acceleration_term = max(0, acceleration) * 7.5
drs_term = 38 if DRS is open else 0

deploy_kW = min(350, throttle_term + acceleration_term + drs_term)
```

This detects high-load acceleration where electrical assistance is plausible.
DRS is included as an opportunity signal, not because DRS itself consumes ERS.

## Inferred Harvest Power

Harvest is considered possible when braking is present, or when the car is
lifting and decelerating:

```text
brake >= 2
or
(throttle <= 25% and acceleration < -0.8)
```

Power terms:

```text
brake_term = min(230, brake * 2.6)
coast_term = 38 if throttle <= 20% else 0
deceleration_term = max(0, -acceleration) * 9.5

harvest_kW = min(350, brake_term + coast_term + deceleration_term)
```

Sample energy:

```text
energy_MJ = power_kW * dt_seconds / 1000
```

Window totals are the sum of inferred sample energy.

## Energy Balance, Risk, and Call

```text
net_MJ = deploy_MJ - harvest_MJ
```

| Balance | Rule |
| --- | --- |
| Deployment heavy | `net_MJ > 0.35` |
| Harvest heavy | `net_MJ < -0.35` |
| Balanced | Otherwise |

Risk is low confidence with fewer than eight samples. It is high when net
deployment exceeds 1.0 MJ and deployment exceeds harvest by more than 25%.
Positive net deployment above 0.35 MJ is medium; other sufficiently sampled
windows are low.

The pit-wall call translates that state:

| Condition | Call |
| --- | --- |
| High risk | Save exits before next attack zone |
| `net_MJ < -0.6` | Available to spend on next straight |
| Medium risk | Prioritize defense, harvest under braking |
| Otherwise | Deployment window sustainable |

The Harvest-vs-Deploy chart compares these totals and absolute net imbalance for
all drivers.

## SOC Proxy

True SOC is unavailable. The project uses a bounded reserve indicator:

```text
SOC_proxy = clamp(
    50 + (harvest_MJ - deploy_MJ) * 18,
    5,
    95
)
```

With fewer than four samples the result defaults to 50% and low confidence.
Confidence becomes medium at 30 samples and high at 90 samples.

This is a race-window balance proxy. It does not integrate real battery energy,
efficiency, loss, temperature, or ECU limits.

## Battle Pressure

For each driver, the current frame finds the car directly ahead and directly
behind by position.

```text
attack_pressure = max(0, 1 - gap_ahead_m / 320)
defense_pressure = max(0, 1 - gap_behind_m / 260)
```

Missing adjacent cars receive no pressure. The asymmetric distances make
defense pressure decay over a slightly shorter range.

Readiness:

| State | Rule |
| --- | --- |
| READY | SOC >= 62 and max pressure >= 0.45 |
| BUILDING | SOC >= 48 and max pressure >= 0.30 |
| SAVE | SOC < 38 |
| WAIT | Otherwise |

The SOC chart is a donut of driver counts in these readiness categories, not a
plot of measured charge percentage.

## Track-Zone Model

Relative lap distance is divided into ten equal bins:

```text
zone = floor(clamp(relative_distance, 0, 0.999) * 10)
```

Samples are classified as:

- **DEPLOY** at inferred deployment of at least 120 kW.
- **HARVEST** at inferred harvesting of at least 100 kW.
- **NEUTRAL** otherwise.

For each driver, lap, zone, and phase, the model aggregates energy and average
speed. The API retains the highest 24 energy rows; the chart displays the top
subset with driver, lap, zone, and phase in its label.

Zones are percentages of lap distance, not named FIA marshal sectors or
official 2026 deployment zones.

## Local Action Policy

The visible policy chooses among `SPEND`, `HOLD`, and `HARVEST`.

Additional features:

```text
straight_value =
    clamp((speed - 170) / 120, 0, 1)
    * clamp(throttle / 100, 0, 1)

harvest_value =
    clamp(brake / 70, 0, 1)
    + 0.35 when throttle < 25 and speed > 120

depletion_penalty = max(0, net_MJ) * 0.32
reserve_credit = max(0, harvest_MJ - deploy_MJ) * 0.18
```

Action scores:

```text
SPEND =
    100 * (
        0.48 * attack_pressure
        + 0.30 * defense_pressure
        + 0.22 * straight_value
    )
    - 100 * depletion_penalty

HOLD =
    100 * (
        0.34 * defense_pressure
        + 0.26 * straight_value
        + 0.22 * reserve_credit
        + 0.18 * max(0, 1 - abs(net_MJ))
    )

HARVEST =
    100 * (
        0.54 * harvest_value
        + 0.26 * depletion_penalty
        + 0.20 * max(0, 1 - attack_pressure)
    )
```

The largest score becomes the action, then the displayed score is clamped to
0-100.

### Relationship to ECMS

Equivalent Consumption Minimization Strategy (ECMS) performs instantaneous
optimization by expressing electrical use as an equivalent fuel cost. The
foundational work by Paganelli et al. is
[Simulation and assessment of power control strategies for a parallel hybrid
car](https://doi.org/10.1243/0954407001527583). Serrao, Onori, and Rizzoni later
compared ECMS with dynamic programming and Pontryagin's minimum principle in
[A Comparative Analysis of Energy Management Strategies for Hybrid Electric
Vehicles](https://doi.org/10.1115/1.4003267).

This dashboard is ECMS-inspired because it scores actions locally while
penalizing energy depletion and valuing reserve. It is not formal ECMS: it does
not model equivalent fuel consumption, an equivalence factor, ICE efficiency,
or a real power split. The UI label `RL/ECMS policy` identifies the research
direction, while the implementation remains an explainable surrogate.

## Short-Horizon Simulator Value

The selected local action receives a projected value:

```text
pressure = max(attack_pressure, defense_pressure)
```

For `SPEND`:

```text
value =
    0.34 * pressure
    + 0.08 * max(0, SOC - 50) / 50
    - 0.05 * max(0, net_MJ)
```

For `HARVEST`:

```text
value =
    -0.08
    + 0.22 * max(0, 45 - SOC) / 45
    + 0.04 * max(0, net_MJ)
```

For `HOLD`:

```text
value =
    0.06
    + 0.16 * pressure
    + 0.08 * max(0, 65 - SOC) / 65
```

The value is displayed as a relative seconds-value indicator beside the action
score. It is for comparison inside the current model and has not been calibrated
as literal observed lap-time gain.

## Lift-and-Coast Recovery

A candidate is created when:

```text
speed > 120 km/h
throttle < 35%
acceleration < -0.3 km/h/s
```

Estimated recovery and time cost:

```text
recover_MJ =
    min(350, max(55, harvest_kW + 42))
    * min(2.2, max(0.6, dt))
    / 1000

time_loss_s = 0.025 + max(0, speed_km_h - 150) / 1000
efficiency = recover_MJ / max(0.02, time_loss_s)
```

The backend keeps up to two strongest candidates per driver. The current
Recovery Opportunity chart intentionally uses the broader per-driver harvest
totals rather than those sparse points, so the full field remains visible.

## RL-Compatible Environment

`BatteryEnergyEnvironment` is a small Gym-like environment with four actions:

```text
SPEND, HOLD, HARVEST, LIFT
```

It is suitable for offline policy research against this proxy model. It is not
registered as an OpenAI Gym/Gymnasium environment and has no external RL
dependency.

### State

The raw state contains:

```text
lap, relative distance, position, speed, throttle, brake, DRS,
SOC proxy, attack pressure, defense pressure, harvest opportunity
```

The training vector excludes lap and normalizes ten features:

```text
relative_distance
position / 20
speed / 360
throttle / 100
brake / 100
DRS as 0 or 1
SOC / 100
attack_pressure
defense_pressure
harvest_opportunity
```

Every value is clamped to 0-1.

### State Transition

SOC begins at 50 and remains between 5 and 95:

```text
SPEND:   SOC -= max(0.6, deploy_kW / 90)
HARVEST: SOC += max(0.5, harvest_kW / 110)
LIFT:    SOC += max(0.8, (harvest_kW + 50) / 95)
HOLD:    SOC += clamp((harvest_kW - deploy_kW) / 220, -0.25, 0.35)
```

These are proxy transition coefficients, not an electrochemical battery model.

### Reward

Let:

```text
pressure = max(attack_pressure, defense_pressure)
straight_value =
    clamp((speed - 160) / 130, 0, 1)
    * clamp(throttle / 100, 0, 1)
```

Rewards:

```text
SPEND:
    +0.75 * pressure
    +0.35 * straight_value
    -0.45 when SOC < 30
    -max(0, deploy_kW - 250) / 700

HARVEST:
    +0.55 * harvest_opportunity
    +0.20 * max(0, 45 - SOC) / 45
    -0.22 * pressure

LIFT:
    +0.75 * harvest_opportunity
    +0.30 * max(0, 40 - SOC) / 40
    -0.32 * pressure
    -0.08

HOLD:
    +0.18 * pressure
    +0.16 * max(0, 65 - SOC) / 65
    -0.08 * harvest_opportunity
```

Every action also receives:

```text
min(0.12, harvest_kW / 1800)
```

The reward balances immediate battle value, reserve recovery, and opportunity
cost. It does not yet include fuel, battery aging, thermal limits, lap-time
dynamics, or terminal SOC constraint.

## Heuristic Policy

The policy labeled `RL heuristic` is deterministic:

```text
if SOC >= 58 and pressure >= 0.42 and speed > 150:
    SPEND
elif harvest_opportunity >= 0.55 and pressure < 0.50:
    HARVEST
elif SOC < 34 and harvest_opportunity >= 0.25:
    LIFT
else:
    HOLD
```

No parameters have been learned. The name means it is the candidate policy
inside the RL-style environment.

## Baseline Comparison

Each driver is rolled out with:

- Heuristic policy.
- Always spend.
- Always harvest.
- Always hold.

Rollouts stop at the end of sampled frames or 120 transitions. The chart reports:

- Best policy reward.
- Heuristic reward minus Hold reward.
- Heuristic final SOC scaled for visualization.
- Heuristic action mix in the API result.

Baselines give reward context. A positive heuristic-vs-Hold value only means the
heuristic scored better under this environment's reward function.

## Relationship to RL Research

RL is a natural direction for hybrid energy management because the controller
must trade immediate power against future reserve under changing demand. A
recent open review is
[Reinforcement learning-based energy management for hybrid electric vehicles:
methods, challenges, and research gaps](https://doi.org/10.1016/j.egyai.2025.100514).

Formula One-specific optimization context is discussed in Javed and Samuel,
[Energy Optimal Control for Formula One Race Car](https://doi.org/10.4271/2022-01-1043),
which compares model-based optimization with dynamic programming in a
high-fidelity powertrain simulator.

The project adopts the state/action/reward framing, baseline rollouts, and
offline-simulation direction from this broader body of work. It does not claim
their fidelity or results.

## What Is Needed for a Trained RL Controller

A defensible trained model would need:

1. A calibrated vehicle longitudinal-dynamics and powertrain simulator.
2. Circuit gradient, curvature, braking, grip, and weather inputs.
3. Real or defensible synthetic SOC and MGU-K power labels.
4. Current FIA energy, deployment-zone, and mode constraints.
5. Terminal SOC, thermal, reliability, fuel, and lap-time objectives.
6. Offline train/validation/test splits by event and season.
7. Comparison with Hold, rule-based, ECMS, dynamic programming, and MPC
   baselines.
8. Sensitivity and out-of-distribution testing.
9. Uncertainty estimates and safe action masking.
10. A model card that prevents proxy reward from being mistaken for real
    performance.

Algorithms worth evaluating after simulator calibration include discrete DQN,
PPO for stable bounded policies, SAC for continuous power requests, constrained
or Lagrangian RL for energy limits, offline RL for logged sessions, and MPC/RL
hybrids. Selection should follow the final action space and validation target,
not fashion.
