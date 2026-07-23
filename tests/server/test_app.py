import time

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")

from fastapi.testclient import TestClient

from src.server.app import create_app
from src.server.replay import HeadlessReplayController
from .test_replay import build_dataset


@pytest.fixture
def client():
    controller = HeadlessReplayController()
    controller.set_dataset(build_dataset(), autoplay=False)
    with TestClient(create_app(controller=controller)) as test_client:
        yield test_client


def test_dashboard_and_health_endpoints(client):
    response = client.get("/")
    assert response.status_code == 200
    assert "Race Intelligence" in response.text

    health = client.get("/api/health").json()
    assert health == {"status": "ready", "ready": True, "progress": 0.0, "message": "", "error": None}
    assert client.get("/api/bootstrap").json()["track_geometry"]["x"]


def test_analysis_and_shared_control_endpoints(client):
    analyses = client.get("/api/analyses", params={"primary": "AAA", "comparison": "BBB", "risk": .7})
    assert analyses.status_code == 200
    assert analyses.json()["selection"]["risk"] == .7

    play = client.post("/api/control", json={"action": "play"})
    assert play.status_code == 200
    assert play.json()["paused"] is False

    invalid = client.post("/api/control", json={"action": "invalid"})
    assert invalid.status_code == 400


def test_websocket_streams_dashboard_state(client):
    with client.websocket_connect("/ws?primary=AAA&comparison=BBB&risk=0.4") as websocket:
        message = websocket.receive_json()
    assert message["type"] == "dashboard"
    assert message["state"]["ready"] is True
    assert message["analyses"]["selection"]["primary"] == "AAA"


def test_catalog_and_session_change_endpoints():
    controller = HeadlessReplayController()
    controller.set_dataset(build_dataset(), autoplay=False)

    def fake_catalog(year):
        return {"year": year, "events": [{"round": 7, "name": "New GP", "sessions": ["FP1", "SQ", "S", "R"]}]}

    def fake_dataset(year, round_number, session_type, refresh):
        dataset = build_dataset()
        dataset.session_info.update({
            "event_name": "New GP",
            "year": year,
            "round": round_number,
            "session_type": "Sprint" if session_type == "S" else "Race",
        })
        return dataset

    app = create_app(controller=controller, dataset_loader=fake_dataset, catalog_loader=fake_catalog)
    with TestClient(app) as test_client:
        catalog = test_client.get("/api/catalog", params={"year": 2024})
        assert catalog.status_code == 200
        assert catalog.json()["events"][0]["sessions"] == ["FP1", "SQ", "S", "R"]

        revision = controller.revision
        response = test_client.post(
            "/api/session",
            json={"year": 2024, "round_number": 7, "session_type": "S", "autoplay": False},
        )
        assert response.status_code == 200
        for _ in range(50):
            if controller.revision > revision:
                break
            time.sleep(.01)

        state = test_client.get("/api/state").json()
        assert state["revision"] == revision + 1
        assert state["session"]["event_name"] == "New GP"
        assert state["session"]["session_type"] == "Sprint"
        assert state["paused"] is True


def test_session_change_validates_request(client):
    response = client.post("/api/session", json={"year": "soon", "round_number": 1})
    assert response.status_code == 400
