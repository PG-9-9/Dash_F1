# Research and Credits

## Project Attribution

This project has been developed over several months as a modular,
server-oriented Formula 1 replay and AI engineering platform.

The replay-dashboard concept was inspired by:

- [IAmTomShaw/f1-race-replay](https://github.com/IAmTomShaw/f1-race-replay),
  an interactive Formula 1 race visualization and data-analysis project by Tom
  Shaw.

The data-access foundation is:

- [theOehrly/Fast-F1](https://github.com/theOehrly/Fast-F1), the Python package
  used to access timing, telemetry, schedules, results, weather, track status,
  and race-control data.

The present codebase is focused on a browser dashboard with a FastAPI replay
server, modular intelligence methods, and experimental AI/optimization work.
AI-assisted coding was used to improve implementation efficiency. Assisted
changes remained under direct supervision within their owning modules, were
manually reviewed, and were validated through manually authored test cases
appropriate to their behavior. This disclosure credits the development process
without replacing responsibility for engineering judgment and validation.

Neither upstream project nor any cited researcher endorses this project.

## Data and Platform References

### FastF1

- [FastF1 documentation](https://docs.fastf1.dev/)
- [Timing and Telemetry Data](https://docs.fastf1.dev/core.html)
- [Requests and Caching](https://docs.fastf1.dev/fastf1.html)

FastF1 supplies the source-facing API and domain data structures. This project
adds session preparation, replay synchronization, web delivery, and its own
analysis methods.

## Hybrid Energy Management Research

### ECMS

Gino Paganelli, Thierry-Marie Guerra, Stephane Delprat, Jean-Jacques Santin,
Michel Delhom, and Eric Combes,
[Simulation and assessment of power control strategies for a parallel hybrid
car](https://doi.org/10.1243/0954407001527583), 2000.

This work describes instantaneous minimization of equivalent fuel flow with a
charge-sustaining objective and is a foundational ECMS reference.

Lorenzo Serrao, Simona Onori, and Giorgio Rizzoni,
[A Comparative Analysis of Energy Management Strategies for Hybrid Electric
Vehicles](https://doi.org/10.1115/1.4003267), 2011.

Compares dynamic programming, Pontryagin's minimum principle, and ECMS under a
common formalization.

The dashboard's local action score is ECMS-inspired but does not implement
equivalent fuel consumption or a calibrated equivalence factor.

### Formula One Energy Optimization

Hassan Javed and Stephen Samuel,
[Energy Optimal Control for Formula One Race
Car](https://doi.org/10.4271/2022-01-1043), SAE Technical Paper, 2022.

This paper formulates F1 hybrid powertrain energy management with a detailed
model, constrained optimization, genetic algorithms, and dynamic-programming
comparison. It supports the project direction of testing rule-based control
against optimization baselines in a simulator.

The paper studies an earlier regulatory generation. Its numerical constraints
must not be applied directly to 2026.

### Reinforcement Learning for Energy Management

[Reinforcement learning-based energy management for hybrid electric vehicles:
A comprehensive up-to-date review on methods, challenges, and research
gaps](https://doi.org/10.1016/j.egyai.2025.100514), *Energy and AI*, 2025.

The review motivates state/action/reward formulations, simulator-based
evaluation, and comparison of RL methods for hybrid energy management.

The project's `BatteryEnergyEnvironment` follows that research pattern at proxy
fidelity. The included policy is deterministic and has not been trained.

## FIA 2026 References

- [A New Era of Competition: FIA showcases future-focused Formula 1 regulations
  for 2026 and beyond](https://www.fia.com/news/new-era-competition-fia-showcases-future-focused-formula-1-regulations-2026-and-beyond)
- [2026 Formula 1 Power Unit Technical
  Regulations](https://www.fia.com/sites/default/files/fia_2026_formula_1_technical_regulations_pu_-_issue_3_-_2023-06-20.pdf)
- [Refinements to the 2026 FIA Formula 1 regulations agreed by all
  stakeholders](https://www.fia.com/news/refinements-2026-fia-formula-1-regulations-agreed-all-stakeholders),
  April 2026
- [Current FIA Formula 1 regulation documents](https://www.fia.com/regulation/category/110)

The project's 350 kW cap follows the published 2026 electrical-power scale.
Current FIA refinements use different limits in different lap regions and
conditions. The code does not model all those distinctions.

## Methods Developed in This Project

The following are project-specific implementations rather than direct
reproductions of a cited paper:

- Public-telemetry ERS deployment and harvest proxy.
- Bounded SOC reserve proxy.
- Battle-pressure energy action score.
- Lift-and-coast opportunity heuristic.
- Battery rollout state transition and reward coefficients.
- Seeded 400-run finish simulation.
- Battle and clean position-swap detection.
- Pit-cycle outcome comparison.
- Tyre health and confidence presentation.
- Constrained strategy trajectory evaluator and diversity filter.

Their exact definitions are documented in
[Race Intelligence](Race-Intelligence.md),
[Strategy Flow](Strategy-Flow.md), and
[Battery Intelligence](Battery-Intelligence.md).

## Trademark and Independence Notice

Formula 1, F1, FIA Formula One World Championship, Grand Prix, and related marks
are the property of their respective owners.

F1 Race Intelligence is an independent, unofficial research and visualization
project. It is not affiliated with or endorsed by Formula 1, the FIA, FastF1,
any racing team, any driver, or any power-unit manufacturer.

## Citation Practice

When publishing results produced with this project:

1. Credit this project and version/commit.
2. Credit FastF1 as the data-access library.
3. Identify the source season, event, session, and replay point.
4. State whether a number is sourced, derived, inferred, or simulated.
5. Cite the relevant ECMS, RL, F1 optimization, or FIA source when discussing
   those methods or constraints.
6. Include the limitations from [Model Boundaries](Model-Boundaries.md).
