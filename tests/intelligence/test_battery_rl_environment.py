from src.intelligence.battery_rl_environment import (
    ACTIONS,
    BatteryEnergyEnvironment,
    compare_energy_policies,
    heuristic_energy_policy,
)


def _frame(t, lap=1, a_position=2, b_position=1, throttle=95, brake=0, speed=260):
    return {
        "t": t,
        "lap": lap,
        "drivers": {
            "AAA": {
                "position": a_position,
                "lap": lap,
                "dist": 1000 + t * 70,
                "rel_dist": (t % 10) / 10,
                "speed": speed,
                "throttle": throttle,
                "brake": brake,
                "drs": 12,
            },
            "BBB": {
                "position": b_position,
                "lap": lap,
                "dist": 1060 + t * 68,
                "rel_dist": (t % 10) / 10,
                "speed": speed - 8,
                "throttle": max(0, throttle - 8),
                "brake": brake,
                "drs": 0,
            },
        },
    }


def _frames():
    values = []
    for t in range(40):
        if t % 8 in (5, 6):
            values.append(_frame(t, throttle=12, brake=35, speed=210 - t % 5))
        else:
            values.append(_frame(t, throttle=92, brake=0, speed=240 + t % 12))
    return values


def test_environment_exposes_normalized_state_and_steps():
    env = BatteryEnergyEnvironment(_frames(), "AAA", sample_step=2)
    state = env.reset()

    assert len(state.vector()) == 10
    assert all(0.0 <= value <= 1.0 for value in state.vector())

    result = env.step("SPEND")
    assert result.action in ACTIONS
    assert result.reward == result.reward
    assert 5 <= result.soc <= 95


def test_heuristic_policy_and_comparison_return_actionable_rows():
    env = BatteryEnergyEnvironment(_frames(), "AAA", sample_step=2)
    rollout = env.rollout(heuristic_energy_policy, horizon=10)

    assert rollout["steps"] == 10
    assert sum(rollout["actions"].values()) == 10

    rows = compare_energy_policies(_frames(), ["AAA", "BBB"])
    assert len(rows) == 2
    assert rows[0][1] in {"RL heuristic", "Spend all", "Harvest all", "Hold"}
