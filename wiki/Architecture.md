# Architecture

F1 Race Intelligence is a server-owned replay system with a lightweight browser
client. The architecture separates data acquisition, replay state, intelligence,
transport, and rendering so each layer can evolve independently.

## Runtime Flow

```text
Browser session request
        |
        v
FastAPI session loader (background thread)
        |
        v
FastF1 session + request cache
        |
        v
Parallel driver telemetry processing
        |
        v
Aligned ReplayDataset + computed-data cache
        |
        v
HeadlessReplayController
        |
        +--> replay clock and shared controls
        +--> precomputed overtakes, pits, and position history
        +--> RaceIntelligenceEngine
        |
        v
REST bootstrap/control + WebSocket state/analyses
        |
        v
HTML/CSS/Canvas dashboard
```

## Module Ownership

### Entry point

`main.py` configures FastF1 logging, normalizes compatibility flags, and delegates
to the server CLI.

### Data layer: `src/data/`

| Module | Responsibility |
| --- | --- |
| `cache_session.py` | FastF1 cache activation, session loading, colors, circuit rotation |
| `race_telemetry.py` | Per-driver extraction, interpolation, weather/status/control alignment, frame generation |
| `safety_car.py` | Safety Car position inference for replay frames |

The data layer knows FastF1 and pandas/NumPy structures. It does not know browser
components or HTTP.

### Intelligence layer: `src/intelligence/`

| Module | Responsibility |
| --- | --- |
| `race_intelligence.py` | Battle, pit, tyre, comparison, prediction, reports, analysis packaging |
| `strategy_flow.py` | Constrained strategy trajectory sampling and evaluation |
| `battery_deployment.py` | ERS proxies, zones, SOC, policy, recovery, simulator |
| `battery_rl_environment.py` | State/action/reward environment and baseline rollouts |
| `replay_events.py` | Full-session pit and overtake precomputation |

The intelligence layer consumes plain dictionaries and dataclasses. It does not
depend on FastAPI or browser code.

### Server layer: `src/server/`

| Module | Responsibility |
| --- | --- |
| `app.py` | FastAPI lifecycle, endpoints, WebSocket, CLI and Uvicorn startup |
| `replay.py` | Thread-safe dataset ownership, replay clock, control, state, analysis cache |
| `dataset_loader.py` | FastF1-to-`ReplayDataset` adapter and progress reporting |
| `models.py` | Shared dataset dataclass |
| `sessions.py` | Event catalog and supported session names |
| `dataset_helpers/lap_times.py` | Lap-record normalization |
| `dataset_helpers/track_geometry.py` | Circuit path sampling and fallback derivation |
| `common_helpers/json_helpers.py` | Strict JSON and color normalization |

### Browser layer: `src/server/static/`

| Module | Responsibility |
| --- | --- |
| `index.html` | Semantic dashboard structure |
| `styles.css` | Responsive dashboard presentation and loaders |
| `js/main.js` | Interaction wiring and startup |
| `js/api.js` | REST calls, WebSocket, reconnection, revision refresh |
| `js/state.js` | Shared browser state, labels, colors, formatting |
| `js/session_picker.js` | Calendar/session selection |
| `js/render_state.js` | State and analysis rendering orchestration |
| `js/tables.js` | Incremental leaderboard and generic data tables |
| `js/replay_canvas.js` | Smoothed track animation |
| `js/charts.js` | Active-tab chart orchestration |
| `js/chart_helpers.js` | Reusable Canvas chart primitives |
| `js/battery_charts.js` | Battery-specific chart composition |

The client uses browser-native modules and Canvas. There is no frontend build
step or large chart framework.

## Application Lifecycle

FastAPI's lifespan creates:

1. An asynchronous replay clock.
2. An optional initial session-load task.

The replay clock advances every 40 ms. Session loading runs blocking data work
through `asyncio.to_thread`, keeping the event loop available for health and
progress responses.

On shutdown, background tasks are cancelled and awaited.

## Concurrency and State

`HeadlessReplayController` protects mutable state with `threading.RLock` because
session preparation can finish on a worker thread while API and replay-clock
work occurs concurrently.

The server allows one active session-load task. A second load request receives a
conflict response rather than racing two replacements.

Dataset installation is atomic from the controller's perspective:

- Replace dataset.
- Reset replay and intelligence history.
- Precompute events and position history.
- Reset speed and pause state.
- Clear error and analysis cache.
- Increment revision.

The browser notices the revision change and reloads static session metadata
before reconnecting.

## Analysis Cache

Analysis is substantially more expensive than core replay state. Results are
cached by:

```text
replay_second, primary_driver, comparison_driver, rounded_risk
```

State can therefore stream four times per second while the full intelligence
bundle is recomputed at most once per replay second for a selection.

Replay controls invalidate the cache key.

## Client Performance Design

The browser avoids unnecessary work through:

- WebSocket state rather than repeated polling after bootstrap.
- Incremental leaderboard row reuse.
- Table signatures that skip unchanged DOM replacement.
- Active-tab-only chart rendering.
- Animation-frame scheduling and stale-generation cancellation.
- Canvas track interpolation between server states.
- GZip middleware for larger HTTP responses.
- No frontend framework or chart-library runtime.

## Extension Rules

Place code according to ownership:

- FastF1 normalization belongs in `src/data` or dataset helpers.
- A reusable analysis belongs in `src/intelligence`.
- HTTP/session/replay concerns belong in `src/server`.
- Reusable browser chart primitives belong in `chart_helpers.js`.
- A feature-specific chart belongs in its feature chart module.
- A helper used by only one component stays with that component.
- A helper used by multiple components moves to an existing shared helper
  module with a precise name.

Avoid adding a new abstraction solely to reduce line count. Add one when it
creates a real ownership boundary or removes meaningful duplication.

## Deployment Shape

The process is stateless with respect to user identity but stateful with respect
to the active replay. Running several workers behind a load balancer would give
each worker a different replay cursor unless shared state is introduced.

For the current design, deploy one application worker per dashboard instance.
A production scale-out design would need a shared replay coordinator, pub/sub
state distribution, sticky sessions, or read-only replica streams.

See [Deployment](Deployment.md) and [API Reference](API-Reference.md).
