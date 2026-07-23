# Testing and Development

## Development Setup

```bash
python3 -m venv .venv-server
source .venv-server/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements-dev.txt
```

`requirements-dev.txt` includes the runtime requirements and adds pytest,
pytest-mock, and HTTPX for server tests.

## Run the Test Suite

```bash
pytest
```

The suite covers:

- Time, tyre, season, and settings utilities.
- Module import integrity.
- Replay controls and state serialization.
- Strict handling of real-world `NaN` values.
- Track-geometry fallback.
- Health, catalog, session-change, analysis, control, and WebSocket endpoints.
- Overtake and pit-event precomputation.
- Race-intelligence outputs.
- External lap-data normalization.
- Strategy diversity and finished-race behavior.
- Battery environment states, actions, rewards, policy, and baselines.

## JavaScript Syntax

The client uses native ES modules. Check every module with:

```bash
node --check src/server/static/js/*.js
```

This validates syntax but does not replace browser interaction tests.

## Manual Dashboard Check

Start the server and verify:

1. Loading percentage moves and resolves.
2. Overview track, classification, battle table, and telemetry render.
3. Play, pause, seek, step, restart, and speed affect server state.
4. Year/circuit/session change replaces the full dataset.
5. Practice, Qualifying, Sprint Qualifying, Sprint, and Race choices load when
   available.
6. Driver selection updates Strategy, Pace, and Comparison.
7. Driver colors remain consistent across replay and charts.
8. Race Evolution shows both selected drivers.
9. Every chart tab shows a loader before rendering and remains responsive.
10. Battery legends and driver labels stay inside the chart at desktop and
    mobile widths.
11. `/api/health` is ready and `/api/docs` loads.
12. Refreshing the browser reconnects without resetting the server replay.

## Test Data Strategy

Server tests build a small deterministic `ReplayDataset`. This avoids network
calls and keeps behavior repeatable.

Do not make unit tests depend on downloading a live FastF1 session. Add a
separate, explicitly invoked integration check when source compatibility needs
validation.

## Adding an Analysis

1. Implement the calculation in a focused module under `src/intelligence`.
2. Return or package it as an `AnalysisResult`.
3. Add it to `HeadlessReplayController.analyses`.
4. Render it only in a meaningful dashboard view.
5. Reuse chart primitives from `chart_helpers.js`; place feature-specific
   composition in a feature chart module.
6. Add deterministic unit tests for normal, sparse, and non-finite inputs.
7. Document inputs, formula, output, and limitations in the wiki.

## Adding a Data Channel

1. Confirm FastF1 exposes the channel for target sessions.
2. Normalize it in the data layer.
3. Include it in interpolation only when interpolation is semantically valid.
4. Add it to frame serialization.
5. Handle missing values explicitly.
6. Add data-quality and strict-JSON tests.

Discrete categories may require forward-fill or event semantics rather than
linear interpolation.

## Adding an AI Model

Every model contribution should state:

- Prediction or decision target.
- Input channels and their provenance.
- Label or reward definition.
- Training, validation, and test split.
- Baselines.
- Evaluation metrics.
- Uncertainty and abstention behavior.
- Runtime and memory cost.
- Known failure modes.
- Whether output is measured, derived, inferred, or simulated.

Do not label a heuristic as trained AI. Do not call a proxy target ground truth.

## Code Organization

- Keep files focused on one feature or ownership boundary.
- Keep a helper inside its component when used once.
- Move a helper to a shared helper module only when multiple components use it.
- Avoid duplicate parsing, colors, formatting, and Canvas setup.
- Add precise docstrings to Python functions and classes.
- Preserve the framework-free client unless a new dependency solves a measured
  problem that native modules cannot.
- Do not commit cache, computed telemetry, media output, virtual environments,
  or generated coverage data.

## Dependency Changes

Runtime dependencies belong in `requirements.txt`. Test and development tools
belong in `requirements-dev.txt`. The Dockerfile installs only runtime
requirements.

When changing FastF1 or numeric-library versions:

1. Rebuild a session from source.
2. Run strict JSON tests.
3. Compare driver count, lap count, geometry, and key telemetry channels.
4. Run the complete test suite.
5. Update documentation for source/API behavior changes.

## Review Priorities

Code review should focus on:

- Behavioral regressions in replay/session replacement.
- Misleading model claims.
- Source data edge cases.
- Non-finite serialization.
- concurrency around load and control.
- Duplicate or unnecessarily expensive browser rendering.
- Missing tests for shared contracts.

See [Architecture](Architecture.md) for module ownership and
[Model Boundaries](Model-Boundaries.md) for model acceptance criteria.
