"""
Smart Home Monitoring - backend

ESP32 --MQTT--> broker --> this app --> SQLite --> REST API + dashboard
Run:        uvicorn main:app --port 8000      (from the backend folder)
Dashboard:  http://127.0.0.1:8000/
Docs:       http://127.0.0.1:8000/docs
"""
import functools
import json
import os
import sqlite3
import threading
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from typing import Optional

import paho.mqtt.client as mqtt
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

print = functools.partial(print, flush=True)  # show log lines immediately
STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")

# ---------------- config ----------------
MQTT_HOST = os.getenv("MQTT_HOST", "broker.hivemq.com")
MQTT_PORT = int(os.getenv("MQTT_PORT", "1883"))
# Must match MQTT_TOPIC in the ESP32 sketch
MQTT_TOPIC = os.getenv("MQTT_TOPIC", "harshit-smarthome-7f3a/readings")
DB_PATH = os.getenv("DB_PATH", os.path.join(os.path.dirname(__file__), "smarthome.db"))
TARIFF_PER_KWH = float(os.getenv("TARIFF_PER_KWH", "8.0"))  # INR per kWh (flat rate)
MQTT_ENABLED = os.getenv("MQTT_ENABLED", "1") == "1"  # set to 0 for offline tests

# ---------------- database ----------------
_db = sqlite3.connect(DB_PATH, check_same_thread=False)
_db.row_factory = sqlite3.Row
_lock = threading.Lock()
with _lock:
    _db.executescript(
        """
        CREATE TABLE IF NOT EXISTS readings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts TEXT NOT NULL,                 -- ISO-8601 UTC
            appliance_id TEXT NOT NULL,
            voltage REAL NOT NULL,
            current REAL NOT NULL,
            power REAL NOT NULL,
            energy_kwh REAL NOT NULL          -- cumulative since ESP32 boot
        );
        CREATE INDEX IF NOT EXISTS idx_readings_app_ts ON readings(appliance_id, ts);
        """
    )
    _db.commit()


class Reading(BaseModel):
    appliance_id: str = Field(min_length=1, max_length=64)
    voltage: float = Field(ge=0, le=500)
    current: float = Field(ge=0, le=100)
    power: float = Field(ge=0, le=50000)
    energy_kwh: float = Field(ge=0)


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def save_reading(r: Reading) -> dict:
    ts = now_iso()
    with _lock:
        _db.execute(
            "INSERT INTO readings (ts, appliance_id, voltage, current, power, energy_kwh) "
            "VALUES (?,?,?,?,?,?)",
            (ts, r.appliance_id, r.voltage, r.current, r.power, r.energy_kwh),
        )
        _db.commit()
    return {"ts": ts, **r.model_dump()}


# ---------------- MQTT subscriber ----------------
def on_connect(client, userdata, flags, reason_code, properties=None):
    print(f"[mqtt] connected ({reason_code}); subscribing to {MQTT_TOPIC}")
    client.subscribe(MQTT_TOPIC)


def on_message(client, userdata, msg):
    try:
        r = Reading(**json.loads(msg.payload.decode()))
        save_reading(r)
        print(f"[mqtt] saved {r.appliance_id}: {r.voltage}V {r.current}A {r.power}W")
    except Exception as e:  # bad payloads must never kill the subscriber
        print(f"[mqtt] ignored bad message: {e}")


mqtt_client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
mqtt_client.on_connect = on_connect
mqtt_client.on_message = on_message


@asynccontextmanager
async def lifespan(app: FastAPI):
    if MQTT_ENABLED:
        try:
            mqtt_client.connect_async(MQTT_HOST, MQTT_PORT, keepalive=60)
            mqtt_client.loop_start()  # background thread, auto-reconnects
        except Exception as e:
            print(f"[mqtt] could not start: {e}")
    yield
    if MQTT_ENABLED:
        mqtt_client.loop_stop()
        mqtt_client.disconnect()


app = FastAPI(title="Smart Home Monitoring API", lifespan=lifespan)


# ---------------- helpers ----------------
def consumption_kwh(rows) -> float:
    """Sum energy from cumulative counter rows (oldest first); handles ESP32 resets."""
    total, prev = 0.0, None
    for r in rows:
        e = r["energy_kwh"]
        if prev is not None:
            total += e - prev if e >= prev else e  # counter reset -> restarted from 0
        prev = e
    return total


# ---------------- routes ----------------
@app.get("/", include_in_schema=False)
def dashboard():
    return FileResponse(os.path.join(STATIC_DIR, "index.html"))


@app.get("/api/health")
def health():
    return {"status": "ok", "mqtt_connected": mqtt_client.is_connected(), "topic": MQTT_TOPIC}


@app.post("/api/ingest")
def ingest(r: Reading):
    """HTTP alternative to MQTT (also handy for testing without Wokwi)."""
    return save_reading(r)


@app.get("/api/appliances")
def appliances():
    with _lock:
        rows = _db.execute(
            "SELECT appliance_id, COUNT(*) AS n, MAX(ts) AS last_seen "
            "FROM readings GROUP BY appliance_id"
        ).fetchall()
    return [dict(r) for r in rows]


@app.get("/api/latest")
def latest(appliance_id: Optional[str] = None):
    q, args = "SELECT * FROM readings", []
    if appliance_id:
        q += " WHERE appliance_id = ?"
        args.append(appliance_id)
    q += " ORDER BY id DESC LIMIT 1"
    with _lock:
        row = _db.execute(q, args).fetchone()
    if not row:
        raise HTTPException(404, "no readings yet")
    return dict(row)


@app.get("/api/history")
def history(
    appliance_id: Optional[str] = None,
    minutes: int = Query(60, ge=1, le=60 * 24 * 30),
    limit: int = Query(500, ge=1, le=5000),
):
    since = (datetime.now(timezone.utc) - timedelta(minutes=minutes)).isoformat(timespec="seconds")
    q, args = "SELECT * FROM readings WHERE ts >= ?", [since]
    if appliance_id:
        q += " AND appliance_id = ?"
        args.append(appliance_id)
    q += " ORDER BY id DESC LIMIT ?"
    args.append(limit)
    with _lock:
        rows = _db.execute(q, args).fetchall()
    return [dict(r) for r in reversed(rows)]  # oldest first, ready for charts


@app.get("/api/cost")
def cost(appliance_id: Optional[str] = None, hours: int = Query(24, ge=1, le=24 * 30)):
    since = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat(timespec="seconds")
    q = ("SELECT appliance_id, ts, energy_kwh FROM readings WHERE ts >= ?")
    args = [since]
    if appliance_id:
        q += " AND appliance_id = ?"
        args.append(appliance_id)
    q += " ORDER BY appliance_id, id"
    with _lock:
        rows = _db.execute(q, args).fetchall()
    per: dict = {}
    for r in rows:
        per.setdefault(r["appliance_id"], []).append(r)
    out = []
    for app_id, rs in per.items():
        kwh = consumption_kwh(rs)
        out.append({"appliance_id": app_id, "kwh": round(kwh, 5),
                    "cost": round(kwh * TARIFF_PER_KWH, 4)})
    total_kwh = sum(o["kwh"] for o in out)
    return {"hours": hours, "tariff_per_kwh": TARIFF_PER_KWH,
            "total_kwh": round(total_kwh, 5),
            "total_cost": round(total_kwh * TARIFF_PER_KWH, 4),
            "appliances": out}


@app.get("/api/overview")
def overview(hours: int = Query(24, ge=1, le=24 * 30)):
    """One row per appliance: its newest reading plus energy and cost over the last `hours`."""
    with _lock:
        rows = _db.execute(
            "SELECT r.* FROM readings r JOIN "
            "(SELECT appliance_id, MAX(id) AS max_id FROM readings GROUP BY appliance_id) last "
            "ON r.id = last.max_id ORDER BY r.appliance_id"
        ).fetchall()
    costs = {c["appliance_id"]: c for c in cost(hours=hours)["appliances"]}
    out = []
    for r in rows:
        c = costs.get(r["appliance_id"], {"kwh": 0.0, "cost": 0.0})
        out.append({**dict(r), "kwh_period": c["kwh"], "cost_period": c["cost"]})
    return {"hours": hours, "tariff_per_kwh": TARIFF_PER_KWH, "appliances": out}
