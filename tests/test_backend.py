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


# ---------- Phase 4: dashboard ----------
def test_dashboard_page_served():
    r = client.get("/")
    assert r.status_code == 200 and "Smart Home Monitor" in r.text


def test_overview_one_row_per_appliance():
    send("tv", 230, 0.4, kwh=0.0)
    send("tv", 231, 0.6, kwh=0.002)
    o = client.get("/api/overview").json()
    tv = [a for a in o["appliances"] if a["appliance_id"] == "tv"]
    assert len(tv) == 1 and tv[0]["current"] == 0.6
    assert abs(tv[0]["kwh_period"] - 0.002) < 1e-9


# ---------- Phase 5: alerts ----------
import alerts  # noqa: E402


def test_threshold_rules():
    assert alerts.check_thresholds(230, 5, 1150) == []
    kinds = [k for k, _, _ in alerts.check_thresholds(260, 9.5, 2470)]
    assert kinds == ["over_voltage", "over_current", "over_power"]
    assert [k for k, _, _ in alerts.check_thresholds(190, 1, 190)] == ["under_voltage"]
    assert alerts.check_thresholds(0, 0, 0) == []  # device off is not an under-voltage


def test_zscore_rule():
    history = [1000 + (i % 5) for i in range(30)]
    assert alerts.check_zscore(history[:10], 5000) == []          # too little history
    assert alerts.check_zscore(history, 1003) == []               # normal
    assert alerts.check_zscore(history, 1500)[0][0] == "power_anomaly"


def test_over_current_alert_is_stored_once_and_can_be_acked():
    out = send("kettle", 230, 9.6)                 # 9.6 A > 9.0 A limit
    assert [a["kind"] for a in out["alerts"]] == ["over_current", "over_power"]
    again = send("kettle", 230, 9.7)               # within cooldown -> not repeated
    assert again["alerts"] == []
    data = client.get("/api/alerts", params={"appliance_id": "kettle"}).json()
    assert len(data["alerts"]) == 2
    alert_id = data["alerts"][0]["id"]
    assert client.post(f"/api/alerts/{alert_id}/ack").status_code == 200
    left = client.get("/api/alerts", params={"appliance_id": "kettle", "unacknowledged": True}).json()
    assert len(left["alerts"]) == 1
    assert client.post("/api/alerts/999999/ack").status_code == 404


def test_zscore_alert_end_to_end():
    for i in range(25):
        send("pump", 230, 2.0 + 0.01 * (i % 3))    # steady ~460 W
    out = send("pump", 230, 3.5)                   # sudden jump to ~805 W, still under limits
    assert [a["kind"] for a in out["alerts"]] == ["power_anomaly"]


# ---------- Phase 6: maintenance (Isolation Forest) ----------
import random  # noqa: E402

import maintenance  # noqa: E402


def test_model_report_meets_targets():
    report = client.get("/api/maintenance/report").json()
    for name, r in report.items():
        assert r["normal_flagged_%"] <= 3, name        # few false alarms on normal windows
        assert r["drift_detected_%"] >= 90, name
        assert r["unstable_detected_%"] >= 90, name


def test_normal_fridge_stays_healthy():
    rng = random.Random(1)
    for _ in range(30):
        out = send("fridge", rng.gauss(230, 2), rng.gauss(0.8, 0.02))
        assert not any(a["kind"] == "maintenance" for a in out["alerts"])
    status = out["maintenance"]
    assert status["status"] == "ok" and status["health"] >= 80


def test_worn_ac_gets_one_maintenance_notice():
    rng = random.Random(2)
    notices = []
    for _ in range(25):   # 8.5 A instead of 6.5 A: under the 9 A threshold, so only ML can catch it
        out = send("ac", rng.gauss(230, 2), rng.gauss(8.5, 0.15))
        notices += [a for a in out["alerts"] if a["kind"] == "maintenance"]
    assert out["maintenance"]["status"] == "service needed"
    assert len(notices) == 1                              # cooldown stops repeats
    assert "8." in notices[0]["message"] and "6.50 A normal" in notices[0]["message"]
    names = {a["appliance_id"]: a for a in client.get("/api/maintenance").json()["appliances"]}
    assert names["ac"]["status"] == "service needed"


def test_unknown_appliance_has_no_model():
    assert send("toaster", 230, 3)["maintenance"]["status"] == "no model"


def test_detector_needs_a_full_window_first():
    d = maintenance.MaintenanceDetector(main.detector.models)
    for k in range(maintenance.WINDOW - 1):
        assert d.update("heater", 230, 5.0)["status"] == "learning"
    assert d.update("heater", 230, 5.0)["health"] is not None
