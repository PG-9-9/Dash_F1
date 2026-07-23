# Deployment

The dashboard is designed for server mode. The included Dockerfile and Compose
file provide the most reproducible deployment path for a Linux host or AWS EC2.

## Deployment Model

Run one application process per replay instance. The replay cursor, selected
dataset, and intelligence cache live in process memory. Multiple Uvicorn workers
would not automatically share playback state.

For a team sharing one replay, use one worker and allow multiple WebSocket
clients to connect to it.

## Container Build

```bash
docker build -t f1-race-intelligence .
```

Run with persistent host directories:

```bash
docker run --name f1-dashboard \
  --restart unless-stopped \
  -p 8000:8000 \
  -e F1_YEAR=2025 \
  -e F1_ROUND=12 \
  -e F1_SESSION=R \
  -v f1-fastf1-cache:/app/.fastf1-cache \
  -v f1-computed-data:/app/computed_data \
  f1-race-intelligence
```

Or use:

```bash
docker compose up --build -d
```

## EC2 Outline

1. Create a current Ubuntu or Amazon Linux instance.
2. Choose enough CPU and memory for parallel telemetry preparation. Two vCPUs
   and 4 GiB RAM are a practical starting point; large sessions benefit from
   more.
3. Attach storage with room for FastF1 and computed-data caches.
4. Install Docker and its Compose plugin.
5. Clone the repository.
6. Configure startup year, round, and session in `compose.yaml` or environment.
7. Start with `docker compose up --build -d`.
8. Verify `/api/health`.
9. Put a TLS reverse proxy or managed load balancer in front of the service.

Do not expose development credentials or cache directories through the web
server.

## Security Group

For a direct private test, restrict TCP port `8000` to your own IP.

For production:

- Expose `443` publicly through a reverse proxy/load balancer.
- Optionally expose `80` only for redirect or certificate validation.
- Keep application port `8000` private to the host or VPC.
- Restrict SSH to trusted administration addresses.

The application has no built-in user authentication. Add authentication at the
reverse proxy, identity-aware load balancer, or application layer before making
team data controls public.

## Nginx WebSocket Proxy

A minimal server block needs both HTTP proxying and WebSocket upgrades:

```nginx
server {
    listen 443 ssl http2;
    server_name dashboard.example.com;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_read_timeout 300s;
    }
}
```

Configure certificates and organization-specific headers separately.

## Health Checks

Use:

```text
GET /api/health
```

The container health check starts after 90 seconds to allow an initial
uncached session load. A robust infrastructure health check should consider:

- HTTP reachability.
- `ready` or actively `loading` state.
- Persistent `error` state.
- WebSocket connectivity from the user path.

Do not restart immediately just because a large uncached dataset is still
loading.

## Persistence

Persist:

- `/app/.fastf1-cache`
- `/app/computed_data`

Without persistence, every replacement container may download and recompute the
session. Cache persistence improves launch time and reduces upstream requests.

Cache files are reproducible and can be removed if corrupted, but the next load
will be slower.

## Capacity and Performance

### Session load

The expensive phase is session preparation: FastF1 parsing, per-driver
telemetry extraction, multiprocessing, interpolation, and frame construction.

### Steady state

After load, costs are:

- 25 Hz server replay tick.
- Four state messages per second per client.
- Approximately one analysis bundle per second per selection.
- Canvas rendering in each browser.

Analysis is cached per replay second and selection. Many clients using different
driver/risk selections can increase CPU work.

### Memory

The complete aligned frame dataset is held in memory. Instance sizing should be
tested with the largest target Race session, not only Qualifying or Practice.

## Logs

Container logs:

```bash
docker compose logs -f dashboard
```

Useful operational events include:

- Uvicorn startup and bind address.
- FastF1 source/cache behavior.
- Driver processing progress.
- Dataset load failures.
- Health and endpoint status.

FastF1 logging is suppressed by default. Start with `--verbose` when source-data
diagnostics are required:

```bash
python main.py --verbose --server
```

## Upgrade Procedure

1. Run tests before building.
2. Build a new image.
3. Keep cache volumes intact.
4. Replace the container.
5. Check `/api/health`.
6. Open the dashboard and confirm WebSocket status, track geometry, and charts.

Because replay state is in memory, replacing the process resets playback.

## Scaling Beyond One Process

Horizontal scaling requires an architectural change. Options include:

- A dedicated replay coordinator publishing state through Redis/NATS.
- Read-only web workers subscribing to shared replay events.
- External object storage for prepared datasets.
- Sticky routing for independent replay instances.
- A session identifier in every API and WebSocket route.

Until then, one process with persistent caches is the correct deployment shape.
