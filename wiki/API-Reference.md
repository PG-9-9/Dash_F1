# API Reference

The FastAPI application serves the dashboard, REST endpoints, and a WebSocket
stream from one origin. Interactive OpenAPI documentation is available at
`/api/docs`.

## `GET /`

Returns the dashboard HTML shell.

## `GET /api/health`

Deployment and loading health.

Example while ready:

```json
{
  "status": "ready",
  "ready": true,
  "progress": 0.0,
  "message": "",
  "error": null
}
```

`status` is `loading`, `ready`, or `error`.

## `GET /api/catalog`

Query:

| Field | Type | Rule |
| --- | --- | --- |
| `year` | integer | 1950-2100 |

Response:

```json
{
  "year": 2024,
  "events": [
    {
      "round": 7,
      "name": "Emilia Romagna Grand Prix",
      "location": "Imola",
      "country": "Italy",
      "date": "2024-05-19",
      "sessions": ["FP1", "FP2", "FP3", "Q", "R"]
    }
  ]
}
```

The source schedule may fail or omit old/future events. The server maps source
failure to HTTP `502`.

## `POST /api/session`

Starts background session preparation.

Request:

```json
{
  "year": 2024,
  "round_number": 7,
  "session_type": "R",
  "refresh": false,
  "autoplay": true
}
```

Rules:

- Year: 1950-2100.
- Round: 1-40.
- Session: `R`, `S`, `Q`, `SQ`, `FP1`, `FP2`, or `FP3`.
- Only one session may be loading.

Response:

```json
{
  "status": "loading",
  "year": 2024,
  "round_number": 7,
  "session_type": "R"
}
```

Errors:

| Status | Meaning |
| --- | --- |
| `400` | Invalid year, round, or session |
| `409` | Another session is loading |

Preparation progress is available from health/state/WebSocket messages.

## `GET /api/bootstrap`

Returns the current core state plus static session data:

- Track geometry.
- Driver colors and labels.
- Lap times.
- Supported playback speeds.

Call this at initial page load and after the dataset revision changes.

When no session is ready, the endpoint returns the loading/error core state
without static dataset fields.

## `GET /api/state`

Returns the latest lightweight replay state:

```json
{
  "ready": true,
  "loading": false,
  "revision": 1,
  "frame_index": 2500,
  "total_frames": 100000,
  "progress": 0.025,
  "paused": false,
  "speed": 1.0,
  "time_s": 100.0,
  "lap": 2,
  "total_laps": 57,
  "track_status": "1",
  "weather": {},
  "drivers": [],
  "safety_car": null,
  "session": {}
}
```

Driver entries include code, display name, color, position, coordinates,
distance, lap, tyre, speed, gear, throttle, brake, DRS, and pit state when those
channels are available.

## `GET /api/analyses`

Query:

| Field | Type | Rule |
| --- | --- | --- |
| `primary` | string | Driver code, max 10 characters |
| `comparison` | string | Driver code, max 10 characters |
| `risk` | float | 0.0-1.0 |

Unknown driver codes fall back to the first and second current drivers.

Response keys:

```text
battery
battery_zones
battery_policy
battery_soc
battery_lift
battery_simulator
battery_rl_environment
strategy
battles
undercut
tyres
safety_car
comparison
race_control
prediction
selection
position_history
```

Every named analysis has:

```json
{
  "title": "Analysis name",
  "summary": "Current interpretation",
  "columns": ["Column"],
  "rows": [["Value"]],
  "notes": ["Optional context"]
}
```

HTTP `503` is returned while a session is loading.

## `POST /api/control`

Request:

```json
{
  "action": "speed",
  "value": 4
}
```

Supported actions:

| Action | Value | Behavior |
| --- | --- | --- |
| `play` | ignored | Start playback |
| `pause` | ignored | Pause playback |
| `toggle` | ignored | Toggle play/pause |
| `restart` | ignored | Seek to start and pause |
| `speed` | number | Select nearest supported speed |
| `seek` | float | Seek to normalized 0.0-1.0 progress |
| `step` | seconds | Move backward/forward by seconds |

The response is the updated core state.

Errors:

- `400` for an unsupported action.
- `503` when no replay dataset is loaded.

## `WS /ws`

Query parameters:

```text
primary, comparison, risk
```

The server sends a message every 250 ms.

State-only message:

```json
{
  "type": "state",
  "state": {}
}
```

Approximately every fourth message:

```json
{
  "type": "dashboard",
  "state": {},
  "analyses": {}
}
```

The browser reconnects after 1.5 seconds when the connection closes.

## Operational Notes

- REST and WebSocket have no authentication in the current implementation.
- The active replay and selection-specific analyses are process memory.
- JSON output is recursively sanitized to remove NumPy scalars and non-finite
  values.
- GZip applies to HTTP responses of at least 1000 bytes.
- A reverse proxy must pass WebSocket upgrade headers.

See [Deployment](Deployment.md) before exposing the API publicly.
