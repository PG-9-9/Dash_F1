# Dashboard Guide

The dashboard is a single-page application with seven functional tabs. The
server owns the replay and analysis state, so multiple browser clients can
observe the same running session.

## Global Controls

The top bar is available on every tab.

| Control | Behavior |
| --- | --- |
| Restart | Returns the replay to frame zero and pauses |
| Play/Pause | Toggles server-side playback |
| `-10` / `+10` | Moves the replay by ten seconds |
| Speed | Selects the closest supported speed from 0.1x through 64x |
| Timeline | Seeks to a normalized position in the session |
| Race clock | Displays replay elapsed time |
| Lap counter | Displays the current and total lap |

Controls call the server rather than changing only the local browser. This keeps
the replay state consistent across connected clients.

The left-side connection indicator has three practical states:

- **Live stream**: the WebSocket is connected.
- **Connecting/Reconnecting**: the browser is establishing the stream.
- **Load failed/Server offline**: health or session preparation failed.

## Overview

### Session selection

The selector loads the event catalog for a year, limits the session list to the
selected weekend format, and starts server-side telemetry preparation.

Conventional weekends expose FP1, FP2, FP3, Qualifying, and Race. Sprint
weekends expose FP1, Sprint Qualifying, Sprint, and Race.

### KPI strip

| KPI | Source |
| --- | --- |
| Leader | Lowest current position in the replay frame |
| Track status | Active FastF1 track-status interval |
| Active battles | Number of current modeled battle rows |
| Track temperature | Time-aligned weather telemetry |

Track-status text and border color follow Green, Yellow, Safety Car, VSC, VSC
Ending, and Red Flag states.

### Track position

The Canvas replay projects circuit geometry into the available viewport and
draws each driver in the FastF1-provided driver color. The browser interpolates
between recent server snapshots to keep motion smooth despite a lower network
update rate.

The map is a replay visualization, not centimeter-accurate GPS. Public timing
positions, interpolation, missing samples, and pit-lane geometry can create
visible deviations.

### Classification

The timing tower shows:

- Current position and three-letter race code.
- Driver color.
- Current tyre compound and tyre age.
- Speed.
- Approximate gap to the leader.

The displayed gap is estimated from distance difference divided by current
speed. It is not the official timing-feed interval.

### Battle monitor

Adjacent cars are shown when the estimated gap is at most 3.5 seconds or the car
behind has a speed advantage greater than 20 km/h. States are:

- **ATTACK**: within 1.2 seconds and closing.
- **PRESSURE**: within 2.0 seconds.
- **WATCH**: a wider but relevant battle window.

Validated position swaps appear as recent-pass notes. Pit-lane transitions and
an eight-second pair cooldown reduce false overtake detections.

### Live telemetry

Select a driver to view speed, gear, throttle, brake, DRS, tyre compound, and
tyre life at the current replay point. Driver selections are synchronized with
the Strategy, Pace, and primary Comparison selection.

## Strategy

Select a driver, set risk tolerance, and recalculate. The model returns up to
eight ranked terminal strategy trajectories.

The table contains:

- Sequential pit and pace instructions.
- Modeled remaining time.
- Expected finish position and places gained/lost.
- Strategy risk.
- Flow reward.

The chart compares reward with scaled risk. Risk tolerance affects the reward
penalty and the probability of sampling aggressive/multi-stop plans. Full model
details are in [Strategy Flow](Strategy-Flow.md).

## Pace and Tyres

### Lap time by lap

Plots the selected driver's valid lap-time entries against lap number. Driver
color remains consistent with the track replay.

### Degradation seconds per lap

Shows the fitted linear slope for every available driver-compound group. A
positive slope means observed lap time increased as tyre age increased.

### Tyre performance table

For each driver and compound, the model reports:

- Number of clean laps.
- Median clean-lap pace.
- Linear degradation in seconds per lap.
- Current age.
- Heuristic tyre health.
- Confidence based on sample count.

Rows with fewer than four laps have low confidence; four to seven have medium
confidence; eight or more have high confidence.

## Operations

### Undercut / overcut

Completed pit events are matched with nearby rival stops within five laps. The
model reports compound change, measured pit phase duration, closest rival, net
position change, and a gain/held/loss verdict.

This is an observed outcome report. It does not isolate every causal factor such
as traffic, Safety Car timing, or a rival's pace.

### Safety Car calls

The model treats status codes for Safety Car and VSC as neutralization. It
estimates effective pit loss as 43% of normal modeled pit loss while active,
then combines that saving with tyre age.

Calls are:

- **PIT NOW** when neutralized, tyre age is at least ten laps, and at least five
  laps remain.
- **PROTECT TRACK POSITION** when fewer than five laps remain.
- **STAY OUT** otherwise.

### Race control intelligence

Messages are classified by text:

- **CRITICAL** for red flag, stop, or disqualification language.
- **ACTION** for penalty, investigation, or Safety Car language.
- **INFO** otherwise.

The table preserves source category, flag, racing number, message time, and
message content.

## Drivers

Select primary and comparison drivers.

### Performance matrix

The matrix compares:

- Current position.
- Median clean lap.
- Recent average speed.
- Tyre age.
- Detected overtakes.
- Observed pit stops.

For each metric, the model marks the driver with the advantage. The summary
reports clean-lap median pace difference.

### Race evolution

Plots both drivers' sampled position against fractional race lap. Position one
is at the top of the chart. History is precomputed from the session and limited
to points at or before the current replay frame, so seeking updates the trace
without waiting to rebuild browser history.

## Prediction

The server runs 400 seeded completion simulations using:

- Current position.
- Median clean-lap pace.
- Remaining laps.
- Tyre age and randomized pit exposure.
- Gaussian pace uncertainty that grows with remaining race distance.

The chart shows win and podium probability. The table adds expected finish,
points probability, and best/worst simulated finish. Results update against the
current replay lap and are reproducible for the same lap and input state.

See [Race Intelligence](Race-Intelligence.md) for the exact scoring logic.

## Battery

The Battery tab contains seven complementary views:

| View | Question answered |
| --- | --- |
| Harvest vs deploy | Which drivers appear deploy-heavy or harvest-heavy? |
| SOC proxy and readiness | How is inferred reserve distributed across readiness states? |
| Deploy/harvest zones | Where on the lap are the largest energy opportunities? |
| Action score | Which driver currently has the strongest SPEND/HOLD/HARVEST call? |
| Recovery opportunity | Which drivers show the most harvest opportunity? |
| Short-horizon value | What is the modeled local value of the current action? |
| Policy vs baseline | How does the heuristic policy compare with fixed-action rollouts? |

All driver series use the same colors as the replay. The views intentionally use
different chart forms so distributions, ranked values, zones, and policy traces
are represented appropriately.

The Battery tab is the most experimental part of the application. Read
[Battery Intelligence](Battery-Intelligence.md) and
[Model Boundaries](Model-Boundaries.md) before treating its output as an
engineering measurement.
