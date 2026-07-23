import json

from src.server.replay import HeadlessReplayController, ReplayDataset, derive_track_geometry


def build_dataset():
    frames = []
    for second in range(0, 30):
        a_position, b_position = (2, 1) if second < 8 else (1, 2)
        a_pit = 14 <= second < 18
        frames.append({
            "t": float(second),
            "lap": 2 + second // 10,
            "weather": {"track_temp": 34.5, "air_temp": 24.0, "rain_state": "DRY"},
            "drivers": {
                "AAA": {
                    "position": a_position, "lap": 2 + second // 10,
                    "dist": 5000 + second * 70, "rel_dist": (second % 10) / 10,
                    "x": second * 10, "y": second * 4, "speed": 280,
                    "gear": 7, "throttle": 92, "brake": 0, "drs": 12,
                    "tyre": 1, "tyre_life": 8 + second // 10, "in_pit": a_pit,
                },
                "BBB": {
                    "position": b_position, "lap": 2 + second // 10,
                    "dist": 5040 + second * 68, "rel_dist": (second % 10) / 10,
                    "x": second * 10 - 5, "y": second * 4 - 2, "speed": 272,
                    "gear": 7, "throttle": 86, "brake": 0, "drs": 0,
                    "tyre": 2, "tyre_life": 13 + second // 10, "in_pit": False,
                },
            },
        })
    laps = {
        "AAA": [{"lap": lap, "time_s": 90 + lap * .03, "tyre": 1, "tyre_life": lap, "is_pit": False} for lap in range(2, 12)],
        "BBB": [{"lap": lap, "time_s": 90.4 + lap * .04, "tyre": 2, "tyre_life": lap, "is_pit": False} for lap in range(2, 12)],
    }
    return ReplayDataset(
        frames=frames,
        track_statuses=[{"start_time": 0, "end_time": None, "status": "1"}],
        race_control_messages=[{"time": 5, "category": "Flag", "message": "YELLOW IN SECTOR 1", "flag": "YELLOW"}],
        total_laps=50,
        driver_colors={"AAA": (225, 6, 0), "BBB": (40, 183, 199)},
        session_info={"event_name": "Server Test GP", "year": 2025, "round": 1, "session_type": "Race"},
        track_geometry={"x": [0, 100, 200], "y": [0, 50, 0]},
        lap_times=laps,
    )


def test_headless_replay_controls_and_bootstrap():
    controller = HeadlessReplayController()
    controller.set_dataset(build_dataset(), autoplay=False)

    bootstrap = controller.bootstrap()
    assert bootstrap["ready"] is True
    assert bootstrap["session"]["event_name"] == "Server Test GP"
    assert bootstrap["track_geometry"]["x"] == [0, 100, 200]
    assert bootstrap["driver_colors"]["AAA"] == "#E10600"

    controller.control("play")
    controller.advance(0.4)
    assert controller.core_state()["frame_index"] == 10
    controller.control("speed", 4)
    assert controller.core_state()["speed"] == 4.0
    controller.control("seek", 0.5)
    assert 0.45 <= controller.core_state()["progress"] <= 0.55
    controller.control("restart")
    assert controller.core_state()["frame_index"] == 0
    assert controller.core_state()["paused"] is True


def test_headless_replay_exposes_all_dashboard_analyses():
    controller = HeadlessReplayController()
    controller.set_dataset(build_dataset(), autoplay=False)
    controller.control("seek", 0.95)
    analyses = controller.analyses("AAA", "BBB", 0.65)

    assert set(analyses) == {
        "battery", "battery_zones", "battery_policy", "strategy", "battles", "undercut", "tyres", "safety_car",
        "battery_soc", "battery_lift", "battery_simulator", "battery_rl_environment", "comparison", "race_control", "prediction", "selection", "position_history",
    }
    assert analyses["strategy"]["rows"]
    assert analyses["prediction"]["rows"]
    assert analyses["battery"]["rows"]
    assert analyses["battery_policy"]["rows"]
    assert analyses["battery_soc"]["rows"]
    assert analyses["battery_simulator"]["rows"]
    assert analyses["battery_rl_environment"]["rows"]
    assert analyses["selection"] == {"primary": "AAA", "comparison": "BBB", "risk": 0.65}
    assert analyses["position_history"]["AAA"]
    assert analyses["position_history"]["BBB"]
    assert all(set(point) == {"x", "y"} for point in analyses["position_history"]["AAA"])


def test_loaded_replay_reports_session_switch_loading_and_revision():
    controller = HeadlessReplayController()
    controller.set_dataset(build_dataset(), autoplay=False)
    initial_revision = controller.core_state()["revision"]

    controller.set_loading()
    switching = controller.core_state()
    assert switching["ready"] is True
    assert switching["loading"] is True

    replacement = build_dataset()
    replacement.session_info["event_name"] = "Replacement GP"
    controller.set_dataset(replacement, autoplay=False)
    replaced = controller.core_state()
    assert replaced["revision"] == initial_revision + 1
    assert replaced["session"]["event_name"] == "Replacement GP"


def test_invalid_control_is_rejected():
    controller = HeadlessReplayController()
    controller.set_dataset(build_dataset())
    try:
        controller.control("launch")
    except ValueError as exc:
        assert "Unsupported replay action" in str(exc)
    else:
        raise AssertionError("Unknown control should fail")


def test_real_world_nan_values_are_strict_json_safe():
    dataset = build_dataset()
    dataset.frames[0]["drivers"]["AAA"]["speed"] = float("nan")
    dataset.frames[0]["weather"]["humidity"] = float("nan")
    dataset.track_geometry["x"].append(float("nan"))
    controller = HeadlessReplayController()
    controller.set_dataset(dataset, autoplay=False)

    bootstrap = controller.bootstrap()
    json.dumps(bootstrap, allow_nan=False)
    assert bootstrap["drivers"][1]["speed"] is None
    assert bootstrap["weather"]["humidity"] is None
    assert bootstrap["track_geometry"]["x"][-1] is None


def test_track_geometry_can_be_recovered_from_driver_positions():
    geometry = derive_track_geometry(build_dataset().frames, max_points=100)
    assert len(geometry["x"]) >= 10
    assert len(geometry["x"]) == len(geometry["y"])
