# Getting Started

## Requirements

- Python 3.10 or newer; Python 3.12 matches the Docker image.
- Internet access for a session that is not already cached.
- Enough disk space for FastF1 request data and computed telemetry.
- A modern browser with JavaScript, Canvas, and WebSocket support.

The runtime dependencies are intentionally kept in one file:
`requirements.txt`. Development-only packages are in `requirements-dev.txt`.

## Local Installation

From the repository root:

```bash
python3 -m venv .venv-server
source .venv-server/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

On Windows PowerShell, activate with:

```powershell
.venv-server\Scripts\Activate.ps1
```

## Start the Dashboard

```bash
python main.py --server
```

Open `http://127.0.0.1:8000`.

The default startup selection is:

| Setting | Value |
| --- | --- |
| Year | 2025 |
| Round | 12 |
| Session | Race |
| Host | 127.0.0.1 |
| Port | 8000 |
| Playback | Autoplay |

The `--server` flag is accepted for compatibility and routed to the only
supported runtime: the web dashboard.

## Select a Startup Session

Use command-line arguments:

```bash
python main.py --server \
  --year 2024 \
  --round 7 \
  --session Q \
  --host 0.0.0.0 \
  --port 8000
```

Or use environment variables:

```bash
F1_YEAR=2024 \
F1_ROUND=7 \
F1_SESSION=Q \
F1_HOST=0.0.0.0 \
F1_PORT=8000 \
python main.py --server
```

Supported session codes:

| Code | Session |
| --- | --- |
| `R` | Race |
| `S` | Sprint |
| `Q` | Qualifying |
| `SQ` | Sprint Qualifying |
| `FP1` | Practice 1 |
| `FP2` | Practice 2 |
| `FP3` | Practice 3 |

Use `--paused` to prepare the session without starting the replay. Use
`--refresh-data` to ignore the computed replay pickle and regenerate it from
the FastF1 session.

## Load a Session in the Browser

Open the Overview tab and choose:

1. Championship year.
2. Circuit/event.
3. Session type available for that event.
4. **Load session**.

The server loads only one new session at a time. A request made during an
existing load returns HTTP `409`. The progress overlay reports calendar access,
FastF1 download/load, driver processing, timeline alignment, frame generation,
and dashboard-data preparation as a percentage.

When loading completes, the server increments the dataset revision. The client
then refreshes track geometry, lap data, driver labels, and colors before
reconnecting its WebSocket.

## First Load and Cache

The first load is slower because it may download and parse a full session and
then align every driver's telemetry. Two cache layers reduce later startup time:

- `.fastf1-cache/` stores FastF1 request and parsed API cache data.
- `computed_data/` stores the prepared replay frame bundle.

Both directories are excluded from Git because they can be large and are
reproducible. Keep the cache enabled to reduce source API traffic and avoid rate
limits.

## Docker

```bash
docker compose up --build
```

Open `http://127.0.0.1:8000`.

The Compose service publishes port `8000`, starts the server on `0.0.0.0`, and
persists cache data in `fastf1-cache` and `computed-data` named volumes.

Stop the service with:

```bash
docker compose down
```

The named volumes remain available for the next start.

## Health and API Docs

```bash
curl http://127.0.0.1:8000/api/health
```

A loaded session reports `status: ready`. During preparation it reports
`status: loading`, progress from `0.0` to `1.0`, and a status message.

Interactive OpenAPI documentation is served at:

```text
http://127.0.0.1:8000/api/docs
```

## Common Problems

### The first load appears slow

Leave the page open and watch the percentage. Full telemetry alignment is CPU
and network intensive. A cached reload is substantially faster.

### The calendar or session cannot be downloaded

Confirm internet access, retry later if the source API is rate-limited, and
preserve `.fastf1-cache/` between runs.

### Port 8000 is already in use

```bash
python main.py --server --port 8001
```

Then open `http://127.0.0.1:8001`.

### Track geometry is empty

The loader first samples the fastest lap's telemetry. If that geometry is too
sparse, it derives a circuit path from replay driver positions. A source session
with insufficient positional telemetry may still be incomplete.

### The dashboard says it is reconnecting

Check `/api/health`, confirm a reverse proxy permits WebSocket upgrades, and
verify that the browser can reach the same host and port used for HTTP.

### A session fails after a previous session was loaded

The server publishes the load error and retains the process. Load a known
available session or restart with a valid year, round, and session code.

Continue with the [Dashboard Guide](Dashboard-Guide.md) or
[Deployment](Deployment.md).
