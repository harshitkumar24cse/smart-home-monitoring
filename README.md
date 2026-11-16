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
| `backend/alerts.py` | Threshold and z-score alert rules (Phase 5) |
| `backend/maintenance.py` | Isolation Forest maintenance detector + synthetic training data (Phase 6) |
| `backend/models/report.json` | Model accuracy on unseen synthetic test data |
| `SETUP.bat` / `START_DEMO.bat` | Double-click: install once / run the app |
| `tools/simulate.py` | Sends fake readings over HTTP (normal or with faults) |
| `tests/` | Automated tests (`pytest`), no internet needed |

## Quick start (Windows, no typing needed)
1. Install Python 3.10+ from https://www.python.org/downloads/ (tick **Add Python to PATH**).
2. Download this repo (green **Code** button -> **Download ZIP**) and unzip it.
3. Double-click **`SETUP.bat`** once (installs the packages, needs internet, a few minutes).
4. Double-click **`START_DEMO.bat`** whenever you want to run it. Press **Y** for empty data or **N**
   to keep old data. It shows the address for your phone and opens the dashboard. Keep its window open.
5. Open the Wokwi project (Phase 2), set the knobs to ~230 V and ~5 A, and press Play.

Data is only saved while the `START_DEMO.bat` window is open. Readings sent while it is closed are lost.

**Two laptops at once:** both use the same MQTT topic, so if two Wokwi simulations run at the same time,
both dashboards show the readings from both. Run only one Wokwi at a time, or change `MQTT_TOPIC` in the
sketch and `backend/main.py` to a different unique name.

## Setup by hand (instead of SETUP.bat)
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

### Open the dashboard on your phone
The page fits phone screens. The phone needs to reach the laptop over the network. College and other
public Wi-Fi usually block devices from talking to each other (and may block MQTT port 1883), so use
your **phone's hotspot**: it works anywhere, and the laptop still gets internet for Wokwi and HiveMQ.

1. Turn on the hotspot on your phone and connect the laptop to it.
2. On the laptop run `ipconfig` and note the Wi-Fi adapter's **IPv4 Address**
   (Android hotspot: usually `192.168.x.x`; iPhone: `172.20.10.x`).
3. Start the backend so other devices can reach it (from the `backend` folder):
   ```
   ..\.venv\Scripts\python -m uvicorn main:app --host 0.0.0.0 --port 8000
   ```
4. If Windows Firewall asks, allow Python. Windows often marks a hotspot as a *Public* network, so either
   tick Public too or set the hotspot to *Private* in the laptop's Wi-Fi settings.
5. Start Wokwi (or `tools/simulate.py`) on the laptop as usual.
6. On the phone's browser open `http://<laptop-IP>:8000`, e.g. `http://192.168.43.25:8000`.

Notes: the laptop must stay on with the backend running; the phone only shows the dashboard. The
laptop's IP can change each time it joins the hotspot, so re-check `ipconfig` if the page won't load.
Same idea on home Wi-Fi: phone and laptop just need to be on the same network.

## Phase 5: Alerts
Every reading (from MQTT or `/api/ingest`) is checked in `backend/alerts.py`:

| Rule | Default | Severity |
|---|---|---|
| Over-voltage | > 253 V (230 V + 10%) | critical |
| Under-voltage | < 207 V (230 V - 10%; ~0 V counts as "off", not a sag) | warning |
| Over-current | > 9.0 A | critical |
| Over-power | > 2000 W | warning |
| Power anomaly (z-score) | \|z\| > 3.5 against the appliance's last 60 readings | warning |

z-score: `z = (power - mean) / std` of recent readings. It needs at least 20 earlier readings, and the
std has a small floor so a perfectly flat signal doesn't cause divide-by-zero alarms. 3.0 gave the odd
false alarm from normal sensor noise in testing, so the default is 3.5.

- The same alert (appliance + kind) is not repeated within 60 s (`ALERT_COOLDOWN_S`).
- Alerts are stored in the `alerts` table and re-published over MQTT to `harshit-smarthome-7f3a/alerts`.
- Limits can be changed with environment variables: `VOLTAGE_MIN`, `VOLTAGE_MAX`, `CURRENT_MAX`,
  `POWER_MAX`, `Z_LIMIT`, `Z_WINDOW`.
- On the dashboard: an Alerts panel with an unread count and OK / Acknowledge-all buttons, and the
  live tiles turn red when a value is outside the limits.

| Endpoint | Purpose |
|---|---|
| `GET /api/alerts?appliance_id=&unacknowledged=true&limit=50` | Alerts, newest first, plus unread count |
| `POST /api/alerts/{id}/ack` | Mark one alert as seen |
| `POST /api/alerts/ack-all` | Mark all as seen |
| `GET /api/thresholds` | Current limits |

Try it: `tools/simulate.py --count 30` (builds a baseline), then `--fault spike` or `--fault sag`.
In Wokwi, turn the current pot above 9 A or the voltage pot below 207 V.

## Phase 6: Predictive maintenance (Isolation Forest)
Phase 5 looks at single readings. A failing appliance usually shows up *gradually* instead: its current
creeps up (worn motor, clogged filter) or becomes unstable (loose contact). Phase 6 catches that.

**How it works** (`backend/maintenance.py`)
1. For each new reading, take the last 10 readings of that appliance (~30 s on the ESP32) and compute
   3 features: average voltage, average current, and current spread (std).
2. An Isolation Forest per appliance type (`heater` 5 A, `fridge` 0.8 A, `ac` 6.5 A) has been trained on
   3000 **synthetic normal** windows. It scores each new window; below 0 = abnormal.
3. Health % = share of the last 10 windows that looked normal. Status: `ok`, `watch` (3+ abnormal),
   `service needed` (7+ abnormal).
4. On `service needed` a **maintenance notification** is created in plain words (e.g. "drawing 8.3 A vs
   6.5 A normal"), shown in the dashboard's Alerts panel and banner, and re-published on the MQTT
   alerts topic. At most one per appliance every 10 min (`MAINT_COOLDOWN_S`).

Appliances with no trained profile show "no model" (alerts from Phase 5 still work for them).
The Wokwi sketch publishes as `heater`, so keep its current pot near 5 A and voltage pot near 230 V for
"normal".

**Training and accuracy.** The model is trained automatically on first start if
`backend/models/maintenance.joblib` is missing. To retrain and print the report:
```
.venv\Scripts\python backend/maintenance.py
```
Results on 500 unseen synthetic windows per case:

| Appliance | Normal windows flagged (false alarm) | Current drift caught | Unstable current caught | Low voltage (185-205 V) caught |
|---|---|---|---|---|
| heater | 1.6% | 100% | 100% | 100% |
| fridge | 0.8% | 100% | 100% | 100% |
| ac | 0.0% | 100% | 100% | 52% |

Single false alarms do not cause notifications, because 7 of the last 10 windows must be abnormal.
The AC's weak low-voltage score is because a 205 V sag is close to normal mains variation; voltage sags
are caught anyway by the Phase 5 under-voltage rule.

Design note: with scikit-learn's default `max_samples=256`, only ~20% of drift windows were caught —
points far outside the normal range scored almost the same as the most extreme normal points. Letting
each tree see all training windows (`max_samples=1.0`) fixed this.

| Endpoint | Purpose |
|---|---|
| `GET /api/maintenance` | Health, status and features per appliance |
| `GET /api/maintenance/report` | Model accuracy report from training |

**Try it:** `tools/simulate.py --count 30` (normal), then
`tools/simulate.py --count 60 --fault wear --appliances ac`. Tested 2026-11-16: the maintenance notice
for `ac` came *before* the over-current threshold alert, i.e. the wear was caught early.
