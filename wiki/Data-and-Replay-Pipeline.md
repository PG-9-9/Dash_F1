# Data and Replay Pipeline

## Source Data

The application uses [FastF1](https://docs.fastf1.dev/) to load:

- Event schedules and weekend formats.
- Session results and driver identities.
- Lap timing and compounds.
- Car telemetry, including position, speed, gear, throttle, brake, and DRS.
- Weather data.
- Track status.
- Race-control messages.

FastF1 is an unofficial data interface. Availability and channel quality vary
by season, session, driver, and source API.

## Session Catalog

`src/server/sessions.py` converts the FastF1 event schedule into a small JSON
catalog. Testing events and round zero are excluded. Weekend format determines
the session choices shown by the browser.

The browser currently offers championship years from 2018 through the current
calendar year. The API accepts years from 1950 through 2100, but older sessions
may not have the telemetry required by this dashboard.

## Dataset Preparation

`src/server/dataset_loader.py` coordinates a session load:

1. Enable the configured FastF1 cache.
2. Load the requested FastF1 session with telemetry and weather.
3. Prepare aligned replay frames.
4. Extract the fastest-lap circuit geometry.
5. Derive geometry from driver positions if the fastest-lap path is too sparse.
6. Build lap-time entries.
7. Normalize driver labels, colors, event metadata, track status, and race
   control.
8. Return one `ReplayDataset`.

The loader sends bounded progress callbacks to the replay controller. The
browser reads those values through `/api/health`, `/api/state`, or the WebSocket
stream and displays the percentage.

## Driver Telemetry Preparation

Each driver's laps and telemetry are processed independently. Per-driver arrays
include:

```text
time, X, Y, distance, relative lap distance, lap, tyre, tyre life,
speed, gear, DRS, throttle, brake
```

The workload is distributed across a multiprocessing pool capped by the number
of available CPU cores and drivers.

After processing, the pipeline:

1. Finds the earliest and latest valid telemetry time across all drivers.
2. Creates a shared timeline.
3. Sorts each driver's source samples by time.
4. Uses NumPy interpolation to resample every channel onto the shared timeline.
5. Builds track-status intervals.
6. Normalizes race-control messages.
7. Interpolates weather onto the same replay timeline.
8. Builds frame dictionaries consumed by the replay controller.

This alignment is what allows every driver, the weather, track state, and
controls to move through one shared replay clock.

## Cache Layers

### FastF1 cache

`.fastf1-cache/` is created and passed to `fastf1.Cache.enable_cache`. It stores
raw HTTP responses and parsed API data. Caching improves load time and reduces
the chance of exceeding upstream rate limits.

### Computed replay cache

`computed_data/` stores the expensive aligned replay result as a pickle. The
filename includes the session identity and a Race/Sprint suffix in the current
implementation.

`--refresh-data` bypasses the computed replay pickle and rebuilds it. The FastF1
cache can still satisfy upstream data requests.

Both cache directories are generated runtime data and are excluded from Git.

## ReplayDataset

The in-memory dataset contains:

| Field | Purpose |
| --- | --- |
| `frames` | Time-ordered driver and weather snapshots |
| `track_statuses` | Status intervals with start/end times |
| `race_control_messages` | Normalized source messages |
| `total_laps` | Session lap count used by replay and models |
| `driver_colors` | FastF1 plotting colors |
| `driver_names` | Driver display labels |
| `session_info` | Event, circuit, country, year, round, type, date, length |
| `track_geometry` | Sampled X/Y circuit path |
| `lap_times` | Per-driver lap records for pace and tyre analysis |

## Server Replay

`HeadlessReplayController` owns the active dataset and guards mutable state with
a reentrant lock. Its replay cursor is a floating-point frame index.

The server clock ticks every 40 milliseconds. At 1x:

```text
frame_index += elapsed_seconds * 25
```

Playback speed multiplies that increment. Reaching the final frame pauses the
replay.

Supported replay speeds are:

```text
0.1x, 0.25x, 0.5x, 1x, 2x, 4x, 8x, 16x, 32x, 64x
```

## Precomputed Events and Position History

When a dataset is installed, the controller scans all frames to precompute:

- Position-swap overtake events.
- Pit entry and exit events.
- Per-driver position history sampled every five seconds and whenever position
  changes.

The dashboard filters these records against the current replay frame. This means
a user can open the dashboard or seek midway through a race and still see the
correct historical context.

## Analysis Window

Each intelligence update receives:

- The current frame.
- Current session and track status.
- Lap-time data.
- Race-control events visible at the current time.
- Precomputed overtake and pit history visible at the current time.
- A Battery training window spanning approximately 90 seconds before and after
  the current frame, sampled once per second before the environment applies its
  own sampling.

General telemetry snapshots are retained at approximately one-second intervals,
up to 12,000 points. Battery deployment aggregation uses the most recent 240
snapshots.

## Browser Delivery

The browser first calls `/api/bootstrap` for session metadata, geometry, lap
times, colors, labels, and initial replay state.

It then opens `/ws`:

- State is sent every 250 milliseconds.
- The full analysis bundle is included every fourth message, approximately once
  per second.
- Analysis results are cached by replay second, selected drivers, and risk.

The browser interpolates recent track snapshots inside an animation-frame loop.
Canvas charts redraw only for the active tab and use generation counters to
discard stale scheduled draws.

## Strict JSON Conversion

Telemetry commonly contains NumPy values, pandas values, `NaN`, or infinity.
The server recursively converts output into strict JSON-safe primitives and
replaces non-finite values before sending responses.

Continue with [Architecture](Architecture.md) for ownership boundaries or
[Model Boundaries](Model-Boundaries.md) for source-data caveats.
