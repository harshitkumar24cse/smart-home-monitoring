# Smart Home Monitoring & Maintenance System

Software-only IoT project: a simulated ESP32 (Wokwi) measures voltage and current, sends readings
over MQTT to a FastAPI backend, which stores them in SQLite and serves a live web dashboard,
alerts, and an ML-based maintenance detector.

```
ESP32 (Wokwi) --MQTT--> broker.hivemq.com --> FastAPI backend --> SQLite
                                                   |--> REST API + web dashboard
                                                   |--> threshold / z-score alerts
                                                   '--> Isolation Forest maintenance check
```

## Structure
| Folder / file | What it is |
|---|---|
| `phase1_wokwi/` | ESP32 sketch: 2 potentiometers as voltage/current sensors, OLED display |
| `phase2_wokwi/` | Same sketch plus Wi-Fi and MQTT publishing every 3 s |
| `backend/main.py` | FastAPI app: MQTT subscriber, SQLite storage, REST API |
| `backend/static/index.html` | Web dashboard (Phase 4) |
| `tools/simulate.py` | Sends fake readings over HTTP (normal or with faults) |
| `tests/` | Automated tests (`pytest`), no internet needed |

## Setup (once)
```
python -m venv .venv
.venv\Scripts\python -m pip install -r backend/requirements.txt
```

## Phase 1: ESP32 simulation
1. Go to https://wokwi.com -> New Project -> ESP32.
2. Replace sketch.ino, diagram.json, libraries.txt with the files in `phase1_wokwi/`.
3. Press Play. Turn pot_v (0-250 V) and pot_i (0-10 A).
4. Check the OLED and Serial Monitor: V, I, P = V*I, and kWh accumulating.

Pins: voltage pot -> GPIO34, current pot -> GPIO35, OLED SDA/SCL -> GPIO21/22.

## Phase 2: Wi-Fi + MQTT
Use the files in `phase2_wokwi/` the same way. The ESP32 joins `Wokwi-GUEST` and every 3 s publishes
```json
{"appliance_id":"heater","voltage":230.1,"current":5.02,"power":1155.1,"energy_kwh":0.00321}
```
to `broker.hivemq.com`, topic `harshit-smarthome-7f3a/readings`.

## Phase 3: Backend
Run from the `backend` folder:
```
..\.venv\Scripts\python -m uvicorn main:app --port 8000
```
API docs: http://127.0.0.1:8000/docs

| Endpoint | Purpose |
|---|---|
| `GET /api/health` | Status and whether MQTT is connected |
| `POST /api/ingest` | Save one reading over HTTP (same JSON as MQTT) |
| `GET /api/latest?appliance_id=` | Newest reading |
| `GET /api/history?appliance_id=&minutes=60` | Readings, oldest first |
| `GET /api/appliances` | Appliances seen, reading count, last seen |
| `GET /api/cost?hours=24` | kWh used and cost per appliance (handles ESP32 counter resets) |

Settings (environment variables): `MQTT_HOST`, `MQTT_PORT`, `MQTT_TOPIC`, `DB_PATH`,
`TARIFF_PER_KWH` (default 8 INR/kWh), `MQTT_ENABLED` (set `0` to run offline).

Note: cost counts energy used *between* readings inside the time window, so the very first
reading in the window only sets the starting point.

### Test it without Wokwi
With the backend running, in another terminal:
```
.venv\Scripts\python tools/simulate.py                 # heater, fridge, ac - normal
.venv\Scripts\python tools/simulate.py --fault spike   # also: sag, wear
```
Automated tests:
```
.venv\Scripts\python -m pytest -q
```
Tested 2026-11-16: HTTP ingest, all GET endpoints, and real MQTT through HiveMQ (bad MQTT
messages are ignored without crashing the subscriber).

## Phase 4: Web dashboard
Start the backend, then open **http://127.0.0.1:8000/** (file: `backend/static/index.html`).
It refreshes every 3 s and shows:
- **Live tiles**: voltage, current, power, energy for the selected appliance.
- **History charts**: power, and voltage + current, for 15 min to 24 h.
- **Cost estimate**: kWh and ₹ for the last hour / 24 h / 7 days / 30 days, plus a rough
  monthly projection if the current load kept running.
- **Appliances table**: one row per appliance (latest values, kWh and cost for the period).
  Click a row to switch the tiles and charts to it.

Extra endpoint used by the dashboard: `GET /api/overview?hours=24` (latest reading + period kWh/cost
for every appliance in one call). Charts use Chart.js from the jsDelivr CDN, so the browser needs internet.
