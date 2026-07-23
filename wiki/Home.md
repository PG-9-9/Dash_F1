# F1 Race Intelligence Wiki

This wiki documents the complete behavior, architecture, models, operating
workflow, and limitations of F1 Race Intelligence. It is written against the
current server-only codebase, not the earlier desktop application.

## Purpose

The project combines three concerns:

1. A synchronized replay of publicly available Formula 1 telemetry.
2. A team-oriented dashboard for strategy, pace, operations, and comparison.
3. Experimental AI and optimization methods that produce useful, clearly
   bounded decision-support signals from incomplete public data.

## Documentation Map

| Page | Contents |
| --- | --- |
| [Getting Started](Getting-Started.md) | Local setup, startup options, session loading, and troubleshooting |
| [Dashboard Guide](Dashboard-Guide.md) | Every tab, control, chart, table, and user workflow |
| [Data and Replay Pipeline](Data-and-Replay-Pipeline.md) | FastF1 ingestion, interpolation, cache, frames, and streaming |
| [Race Intelligence](Race-Intelligence.md) | Battles, pit cycles, tyres, Safety Car, comparison, and prediction |
| [Strategy Flow](Strategy-Flow.md) | Constrained strategy generation, reward modeling, and diversity selection |
| [Battery Intelligence](Battery-Intelligence.md) | Exact ERS proxy formulas, policy scores, SOC, simulator, and RL environment |
| [Architecture](Architecture.md) | Component boundaries and runtime ownership |
| [API Reference](API-Reference.md) | REST and WebSocket contracts |
| [Deployment](Deployment.md) | Docker and EC2-oriented production operation |
| [Model Boundaries](Model-Boundaries.md) | Data gaps, interpretation rules, and validation plan |
| [Testing and Development](Testing-and-Development.md) | Test commands and extension workflow |
| [Research and Credits](Research-and-Credits.md) | Project attribution, papers, regulations, and external documentation |

## Capability Summary

The application can replay Race, Sprint, Qualifying, Sprint Qualifying, and
Practice sessions; animate track positions; show classification and live
telemetry; analyze battles, pit cycles, tyres, Safety Car opportunities, and
race control; compare drivers; model strategy alternatives; estimate finish
probabilities; and explore telemetry-derived energy management.

The dashboard is a research and decision-support interface. It does not expose
private team telemetry, control a vehicle, or claim that inferred Battery
metrics are measured ECU values.

## Project Provenance

The replay concept was inspired by
[IAmTomShaw/f1-race-replay](https://github.com/IAmTomShaw/f1-race-replay).
Session and telemetry access is provided through
[FastF1](https://github.com/theOehrly/Fast-F1). The present project has been
developed over several months into a modular browser dashboard with a separate
server, replay engine, intelligence layer, and lightweight client.

The author is an AI Engineer and introduced model-based features where the
public data supports meaningful experimentation. Approximately 20% of the
project was developed with AI-assisted vibe coding for implementation
efficiency. See [Research and Credits](Research-and-Credits.md) for full
attribution.
