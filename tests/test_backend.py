"""Automated tests for the backend. Run from the project folder:  python -m pytest -q
Uses a temporary database and turns MQTT off, so no internet is needed.
"""
import os
import sys
import tempfile

os.environ["MQTT_ENABLED"] = "0"
os.environ["DB_PATH"] = os.path.join(tempfile.mkdtemp(), "test.db")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from fastapi.testclient import TestClient  # noqa: E402

import main  # noqa: E402

client = TestClient(main.app)


def send(appliance="heater", v=230.0, a=5.0, kwh=0.0):
    r = client.post("/api/ingest", json={"appliance_id": appliance, "voltage": v, "current": a,
                                          "power": round(v * a, 1), "energy_kwh": kwh})
    assert r.status_code == 200
    return r.json()


def test_health():
    assert client.get("/api/health").json()["status"] == "ok"


def test_ingest_latest_history_cost():
    for i in range(5):
        send("lamp", 230, 0.5, kwh=0.001 * i)
    latest = client.get("/api/latest", params={"appliance_id": "lamp"}).json()
    assert latest["current"] == 0.5
    hist = client.get("/api/history", params={"appliance_id": "lamp"}).json()
    assert len(hist) == 5 and hist[0]["id"] < hist[-1]["id"]  # oldest first
    cost = client.get("/api/cost", params={"appliance_id": "lamp"}).json()
    assert abs(cost["total_kwh"] - 0.004) < 1e-9
    assert abs(cost["total_cost"] - 0.004 * main.TARIFF_PER_KWH) < 1e-6
    names = [a["appliance_id"] for a in client.get("/api/appliances").json()]
    assert "lamp" in names


def test_counter_reset_is_handled():
    rows = [{"energy_kwh": e} for e in (0.1, 0.2, 0.05, 0.1)]  # ESP32 rebooted after 0.2
    assert abs(main.consumption_kwh(rows) - 0.2) < 1e-9


def test_bad_reading_rejected():
    r = client.post("/api/ingest", json={"appliance_id": "x", "voltage": -5, "current": 1,
                                         "power": 1, "energy_kwh": 0})
    assert r.status_code == 422


def test_unknown_appliance_latest_404():
    assert client.get("/api/latest", params={"appliance_id": "nope"}).status_code == 404
