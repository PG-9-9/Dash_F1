# Model Boundaries and Validation

This page defines what the dashboard can support, what it estimates, and what
must not be inferred from its output.

## Interpretation Levels

| Level | Examples | Appropriate interpretation |
| --- | --- | --- |
| Source-backed | Speed, throttle, brake, DRS, weather, lap records, race control | Public-feed value after alignment/normalization |
| Derived measurement | Median pace, linear degradation, distance-based gap, pit duration | Calculation from source-backed values |
| Heuristic inference | Battle state, Safety Car call, battery deploy/harvest, SOC proxy | Explainable signal based on explicit assumptions |
| Simulation | Finish distribution, strategy trajectory, energy rollout | Outcome inside the project's model |

Never present a heuristic inference or simulation as source telemetry.

## Public Data Limitations

Availability varies by event and session. Potential issues include:

- Missing telemetry for a driver or lap.
- Inaccurate or delayed positions.
- Pit-lane path differences from circuit geometry.
- Discontinuities around retirement, red flags, or session segments.
- Source corrections after an event.
- Missing weather or race-control channels.
- No historical telemetry for many older seasons.
- Source API rate limits or temporary unavailability.

Interpolation makes channels comparable on one timeline but cannot recreate
information that was never present.

## Replay Boundaries

The replay map is a visualization of public position samples. It is not:

- Official GPS.
- A timing transponder replacement.
- A vehicle-dynamics reconstruction.
- Evidence of exact racing line or lateral placement.

The classification is ordered from source-derived position. The displayed
leader gap is an approximate distance/speed conversion, not the official
interval.

## Race Intelligence Boundaries

### Battles and overtakes

Position crossing and proximity can identify likely events. They cannot
distinguish every on-track pass from timing corrections, off-track incidents,
or complex multi-car transitions.

### Pit analysis

Net position change after a stop does not prove an undercut or overcut caused
the result. Traffic, Safety Car timing, pace, damage, and rival strategy remain
confounders.

### Tyres

The degradation slope is fitted to observed clean-lap time versus tyre age. It
does not fully correct for fuel mass, track evolution, weather, traffic, tyre
preparation, setup, or management.

### Safety Car

The `0.43` pit-loss multiplier is a project coefficient. Real savings depend on
circuit, neutralization type, field compression, pit entry timing, and rules.

### Finish prediction

The Monte Carlo model samples its own simplified uncertainty and pit exposure.
Its percentages are not calibrated probabilities unless validated on held-out
races with reliability metrics.

### Strategy

Strategy Flow evaluates simplified pace, degradation, traffic, weather, and pit
loss. It does not model every sporting regulation, incident, team objective, or
competitor reaction. Its coefficients and sampling rules are project-defined.

## Battery Boundaries

The Battery tab does not observe battery telemetry. Specifically, public data
does not expose:

- State-of-charge.
- Usable energy capacity.
- MGU-K power or torque.
- Motor/generator efficiency.
- Battery charge/discharge efficiency.
- Cell voltage, current, temperature, or state-of-health.
- ICE power, fuel use, or power split.
- Driver energy mode.
- Team deployment maps.

Deployment and harvesting are inferred from speed change, controls, and DRS.
SOC is a bounded balance proxy. Scores and rewards reflect the project's
objective function.

The 350 kW constant is a model cap. Current 2026 FIA rules distinguish key
acceleration zones and other lap regions, and may continue to evolve. Always
check the current official regulations before regulatory analysis.

The RL environment is trainable in software terms, but the included policy is
hand-written. No deep RL model is trained or shipped.

## Confidence Language

Use:

- "Source telemetry reports..."
- "The dashboard derives..."
- "The model infers..."
- "The simulation estimates..."
- "Under the current reward function..."

Avoid:

- "The battery is at 64%."
- "The car deployed exactly 2.1 MJ."
- "The model proved this strategy is optimal."
- "The RL agent learned..."
- "The driver will finish P2."

Better:

- "The SOC proxy is 64% over the current window."
- "The model inferred 2.1 MJ of deployment opportunity."
- "This is the highest-reward sampled strategy."
- "The heuristic policy outscored Hold in the proxy environment."
- "P2 is the mean finish across 400 modeled completions."

## Validation Framework

### Data pipeline

- Compare frame channels with FastF1 lap and telemetry samples.
- Test missing and non-finite values.
- Verify session types and event formats.
- Check track geometry fallback.
- Test seek, restart, speed, and dataset revision behavior.

### Race intelligence

- Label a sample of overtakes and pit events manually.
- Report precision, recall, and timing error.
- Evaluate tyre slope against held-out later laps in the same stint.
- Validate pit-loss estimates by circuit.
- Backtest finish probabilities with Brier score and calibration curves.

### Strategy

- Enforce action feasibility with property tests.
- Compare anchors and sampled plans with retrospective race outcomes.
- Evaluate reward sensitivity to every coefficient.
- Report diversity, duplicate rate, and constraint violation rate.
- Compare against no-stop, one-stop, and deterministic search baselines.

### Battery

- Validate proxy phase detection against simulated MGU-K labels.
- Calibrate power coefficients in a vehicle model, not directly against SOC
  assumptions.
- Check terminal SOC conservation and energy balance.
- Evaluate policy reward against dynamic programming or MPC in the same
  simulator.
- Test circuits, weather, race phases, and unseen seasons separately.
- Report results both with and without battle-pressure features.

## Reproducibility

Current stochastic models are seeded:

- Strategy generation seed starts from seven and incorporates lap and position.
- Finish simulation seed starts from 1701 and incorporates current lap.

The same code, prepared dataset, replay point, and selection should produce the
same modeled output. Source API revisions or FastF1 parser changes can alter a
freshly generated dataset.

## Production Readiness Checklist

Before using a model for operational decisions:

1. Pin dependency and data-parser versions.
2. Version the prepared dataset.
3. Version coefficients and model artifacts.
4. Add event-level held-out validation.
5. Publish calibration and failure cases.
6. Add input quality monitoring.
7. Add uncertainty or abstention behavior.
8. Confirm current sporting and technical rules.
9. Require domain-expert review.
10. Preserve human override and source-data visibility.

The current project is strongest as an explainable research dashboard and model
development platform.
