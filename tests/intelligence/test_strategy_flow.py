from src.intelligence.strategy_flow import StrategyContext, StrategyFlowEngine


def test_flow_engine_returns_ranked_diverse_terminal_strategies():
    context = StrategyContext(
        current_lap=15,
        total_laps=57,
        current_compound="MEDIUM",
        tyre_age=15,
        position=5,
        baseline_lap_s=91.2,
        traffic_risk=0.5,
        risk_tolerance=0.55,
    )
    strategies = StrategyFlowEngine(seed=11).generate(context, count=12, samples=300)

    assert len(strategies) == 12
    assert all(item.expected_time_s > 0 and item.reward > 0 for item in strategies)
    assert [item.reward for item in strategies] == sorted(
        [item.reward for item in strategies], reverse=True
    )
    assert len({item.signature for item in strategies}) == len(strategies)
    assert any(any(action.kind == "PIT" for action in item.actions) for item in strategies)
    assert any("PACE" in item.sequence for item in strategies)


def test_flow_engine_handles_finished_race():
    context = StrategyContext(50, 50, "HARD", 20, 2, 88.0)
    strategy = StrategyFlowEngine().generate(context)[0]
    assert strategy.actions == []
    assert strategy.expected_position >= 1
