# Race Intelligence

`RaceIntelligenceEngine` converts replay state into operational summaries. The
methods are deliberately interpretable: each output can be traced to current
telemetry, historical frames, lap records, or a documented heuristic.

## State and Sampling

The engine stores:

- Latest enriched replay payload.
- One-second telemetry snapshots.
- Validated overtakes.
- Pit entry/exit events.
- Optional external practice laps.
- Strategy-flow engine state.

Analysis output uses a common `AnalysisResult` shape:

```text
title, summary, columns, rows, notes
```

This shape is serialized by the server and consumed by tables and charts.

## Overtake Detection

A pass is detected when:

1. An attacker's numerical position improves.
2. A victim's relative position crosses in the opposite direction.
3. Neither car is currently in the pit lane.
4. Neither car was in the pit lane in the prior sample.
5. The same driver pair has not triggered within eight seconds.

The event stores lap, replay time, attacker, victim, resulting position, and
whether the attacker's DRS code indicates an open state.

This detects clean ordering swaps. It cannot prove the sporting cause of every
swap and may miss complex multi-car changes between samples.

## Battle Detection

Drivers are sorted by current position and evaluated in adjacent pairs.

Approximate time gap:

```text
distance_gap_m / max(20, average_pair_speed_km_h / 7.2)
```

The row is retained if the gap is at most 3.5 seconds or the trailing car is
more than 20 km/h faster.

| State | Condition |
| --- | --- |
| ATTACK | Gap <= 1.2 s and trailing car is closing |
| PRESSURE | Gap <= 2.0 s |
| WATCH | Wider retained battle |

## Pit and Undercut/Overcut Analysis

A pit event opens when `in_pit` changes from false to true and closes when it
returns to false. It records entry/exit replay time, lap, position, and tyre
compound.

Completed events are compared with other completed stops within five laps. The
nearest event by entry time is shown as the closest rival.

Net places:

```text
entry_position - current_position
```

Positive is a gain, negative is a loss, and zero is held. This is a practical
outcome comparison, not a causal counterfactual model of the undercut.

## Tyre Performance

Lap records are grouped by driver and compound. A lap is considered clean when
its time is positive and it is not marked as pit-in, pit-out, deleted, or
inaccurate by the available data.

For each group:

- **Median pace** is the median clean lap time.
- **Degradation** is the least-squares slope of lap time against tyre life.
- **Current age** comes from the replay, falling back to the observed group.
- **Health** is a heuristic percentage based on compound cliff age.
- **Confidence** depends on clean-lap count.

Compound cliff ages:

| Compound | Cliff age |
| --- | ---: |
| Soft | 18 laps |
| Medium | 30 laps |
| Hard | 42 laps |
| Intermediate | 30 laps |
| Wet | 38 laps |

Tyre health is:

```text
100 * (1 - age / (cliff_age + 8))
```

clamped to 0-100%.

The linear slope does not separately remove fuel burn, traffic, wind, track
evolution, or driver management. The table therefore calls it an observed
stint trend and exposes sample confidence.

## Safety Car Decision Tool

The model recognizes status codes `4`, `6`, `7`, `SC`, and `VSC` as an active
neutralization.

Normal pit loss is estimated from completed stops when available, with a
fallback. During neutralization:

```text
effective_pit_loss = normal_pit_loss * 0.43
```

Potential saving adds:

```text
normal_pit_loss - effective_pit_loss
    + max(0, tyre_age - 12) * 0.18
```

The call is **PIT NOW** when neutralized, tyre age is at least ten laps, and at
least five laps remain. With fewer than five laps remaining it becomes
**PROTECT TRACK POSITION**; otherwise it is **STAY OUT**.

## Driver Comparison

Two selected drivers are compared on:

| Metric | Advantage rule |
| --- | --- |
| Position | Lower is better |
| Median clean lap | Lower is better |
| Recent average speed | Higher is better |
| Tyre age | Lower is treated as better |
| Overtakes | Higher is better |
| Pit stops | Lower is treated as better |

The summary reports the clean-lap median delta. The position chart comes from
precomputed session history and retains actual driver colors.

## Race Control Priority

Race-control messages are retained up to the current replay time. Priority is
assigned using visible message text:

```text
CRITICAL: RED FLAG, STOP, DISQUALIFIED
ACTION:   PENALTY, INVESTIGATION, SAFETY CAR
INFO:     all other messages
```

The latest 100 messages are displayed. This classification helps scanning but
does not replace an official stewarding system.

## Practice Planner

The engine can normalize JSON or CSV laps with OpenF1/FastF1-like field names.
Accepted concepts include driver, lap number, duration, compound, tyre life,
session, and stint.

The current browser does not expose an upload control, but the engine method is
tested and can be used by a future import endpoint. With imported laps it builds
a five-block program:

1. Installation and systems.
2. Qualifying simulation.
3. High-fuel race run.
4. Alternative long run.
5. Start and pit practice.

Without imported laps it uses current-session clean pace as a proxy.

## Finish Prediction

The prediction model runs 400 seeded Monte Carlo completions. For driver \(d\):

```text
score_d =
    current_position * 5.2
    + median_pace_seconds * remaining_laps
    + randomized_pit_exposure
    + gaussian_uncertainty * remaining_laps
```

Pit exposure is zero with fewer than eight laps remaining. Otherwise it is
sampled up to a fraction of modeled pit loss, with larger exposure for tyres at
least 12 laps old.

Uncertainty standard deviation:

```text
0.28 + remaining_laps / max(25, total_laps) * 0.55
```

Drivers are ranked by ascending score in each simulation. The output reports:

- Mean finish position.
- Win probability.
- Podium probability.
- Points probability.
- Best and worst sampled finish.

The random seed is `1701 + current_lap`, making results repeatable for the same
lap and state. This is a scenario model, not a calibrated betting forecast.

## Summary and Report Support

The engine can also assemble a session summary and plain-text report containing
leader, progress, clean pace, overtakes, pit stops, race control, strategy,
comparison, and prediction sections. These engine capabilities are not
currently exposed as a dashboard export button.

The project removes static panels that do not convey live information; an
unexposed engine method is documented here so future API work can build on a
tested capability without misrepresenting it as a current UI feature.
