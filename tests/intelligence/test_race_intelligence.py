import json

import pytest

from src.intelligence.race_intelligence import RaceIntelligenceEngine, precompute_replay_events


def _lap(lap, time_s, tyre=1, age=1, **extra):
    return {
        "lap": lap,
        "time_s": time_s,
        "tyre": tyre,
        "tyre_life": age,
        "is_pit": False,
        "is_out_lap": False,
        "is_outlier": False,
        **extra,
    }


def _payload(t=100.0, lap=12, a_pos=2, b_pos=1, a_pit=False, b_pit=False):
    return {
        "frame": {
            "t": t,
            "lap": lap,
            "weather": {"rain_state": "DRY"},
            "drivers": {
                "AAA": {
                    "position": a_pos, "lap": lap, "dist": 52000 + t * 45,
                    "speed": 284, "tyre": 1, "tyre_life": 13,
                    "drs": 12, "in_pit": a_pit,
                },
                "BBB": {
                    "position": b_pos, "lap": lap, "dist": 52080 + t * 44,
                    "speed": 271, "tyre": 2, "tyre_life": 18,
                    "drs": 0, "in_pit": b_pit,
                },
            },
        },
        "track_status": "1",
        "session_data": {
            "event_name": "Test Grand Prix", "lap": lap, "total_laps": 50, "time_s": t,
        },
        "lap_times": {
            "AAA": [_lap(n, 89.8 + n * 0.02, 1, n) for n in range(2, 12)],
            "BBB": [_lap(n, 90.2 + n * 0.03, 2, n) for n in range(2, 12)],
        },
        "race_control_events": [
            {"time": 80, "category": "Flag", "flag": "YELLOW", "message": "YELLOW IN SECTOR 2"},
            {"time": 95, "category": "Other", "message": "CAR 7 UNDER INVESTIGATION", "racing_number": "7"},
        ],
    }


@pytest.fixture
def engine():
    value = RaceIntelligenceEngine()
    value.update(_payload())
    value.update(_payload(t=101.0, a_pos=1, b_pos=2))
    value.update(_payload(t=102.0, a_pos=1, b_pos=2, a_pit=True))
    value.update(_payload(t=124.0, lap=13, a_pos=2, b_pos=1, a_pit=False))
    return value


def test_detects_overtakes_and_completed_pit_events(engine):
    assert engine.overtakes[-1]["attacker"] == "AAA"
    assert engine.overtakes[-1]["victim"] == "BBB"
    assert engine.overtakes[-1]["drs"] is True
    assert engine.pit_events[-1]["driver"] == "AAA"
    assert engine.pit_events[-1]["exit_t"] == 124.0


def test_every_intelligence_feature_returns_operational_output(engine):
    results = [
        engine.strategy_analysis("AAA"),
        engine.battles_analysis(),
        engine.undercut_analysis(),
        engine.tyre_analysis(),
        engine.safety_car_analysis(),
        engine.driver_comparison("AAA", "BBB"),
        engine.race_control_analysis(),
        engine.practice_plan("AAA"),
        engine.predictive_analysis(),
        engine.summary_report(),
    ]

    assert len(results) == 10
    assert all(result.title and result.summary for result in results)
    assert all(result.columns for result in results)
    assert all(result.rows for result in results)
    assert len(engine.strategy_analysis("AAA").rows) >= 5
    assert "AAA passed BBB" in "\n".join(engine.battles_analysis().notes)


def test_imports_openf1_style_json_for_practice_planning(engine, tmp_path):
    source = tmp_path / "openf1-laps.json"
    source.write_text(json.dumps([
        {"driver_number": 4, "lap_number": 2, "lap_duration": 92.1, "compound": "MEDIUM", "stint": 1},
        {"driver_number": 4, "lap_number": 3, "lap_duration": 91.8, "compound": "MEDIUM", "stint": 1},
    ]), encoding="utf-8")

    assert engine.import_lap_data(source) == 2
    result = engine.practice_plan("4")
    assert "imported practice data" in result.summary
    assert len(result.rows) == 5


def test_exports_plain_text_report(engine):
    report = engine.report_text("AAA", "BBB")
    assert "F1 RACE INTELLIGENCE REPORT" in report
    assert "DRIVER PERFORMANCE COMPARISON" in report
    assert "PREDICTIVE REPLAY MODE" in report


def test_precomputes_history_for_windows_opened_mid_replay():
    payloads = [
        _payload(t=100.0),
        _payload(t=101.0, a_pos=1, b_pos=2),
        _payload(t=102.0, a_pos=1, b_pos=2, a_pit=True),
        _payload(t=124.0, lap=13, a_pos=2, b_pos=1),
    ]
    history = precompute_replay_events([payload["frame"] for payload in payloads])

    assert [(event["attacker"], event["victim"]) for event in history["overtakes"]] == [("AAA", "BBB")]
    assert history["pit_events"][0]["entry_t"] == 102.0
    assert history["pit_events"][0]["exit_t"] == 124.0

    late_engine = RaceIntelligenceEngine()
    late_payload = payloads[-1]
    late_payload["intelligence_events"] = history
    late_engine.update(late_payload)
    assert late_engine.overtakes == history["overtakes"]
    assert late_engine.pit_events == history["pit_events"]
