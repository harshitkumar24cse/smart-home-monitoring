"""
Phase 6 - predictive maintenance with an Isolation Forest.

Idea
----
Phase 5 alerts look at ONE reading. A failing appliance usually shows up slowly instead:
its current creeps up (worn motor, dirty filter) or becomes unstable (loose contact).
So for each reading we look at a short window of the last WINDOW readings and build 3 features:

    voltage,  mean current over the window,  std of current over the window

An Isolation Forest is trained (one per appliance type) on *synthetic normal* data only.
It learns what "normal" looks like and gives a low score to anything that doesn't fit.

If at least NOTIFY_AFTER of the last WINDOW decisions are "abnormal", we raise a
maintenance notification. Health % = share of recent decisions that were normal.

Retrain and print an evaluation report:   python backend/maintenance.py
"""
import json
import os
import threading
from collections import deque

import joblib
import numpy as np
from sklearn.ensemble import IsolationForest

# Normal current (A) for each appliance type. Voltage is 230 V for all.
# Matches tools/simulate.py; the Wokwi sketch publishes as "heater" (set its current pot near 5 A).
APPLIANCE_PROFILES = {"heater": 5.0, "fridge": 0.8, "ac": 6.5}

WINDOW = 10          # readings per feature window (about 30 s at the ESP32's 3 s rate)
NOTIFY_AFTER = 7     # abnormal decisions out of the last WINDOW before we notify
MODEL_PATH = os.path.join(os.path.dirname(__file__), "models", "maintenance.joblib")
REPORT_PATH = os.path.join(os.path.dirname(__file__), "models", "report.json")


# ---------------- synthetic data ----------------
def window_features(voltages, currents) -> list:
    return [float(np.mean(voltages)), float(np.mean(currents)), float(np.std(currents))]


def make_window(rng, nominal, fault=None):
    """One synthetic window of WINDOW readings -> feature vector."""
    load = nominal * rng.normal(1.0, 0.04)               # normal load varies a little
    v_mean = rng.normal(230, 4)                           # mains wanders a bit
    i_noise = nominal * rng.uniform(0.02, 0.04)           # normal sensor noise

    if fault == "drift":        # worn part: draws 20-50% more current
        load = nominal * rng.uniform(1.2, 1.5)
    elif fault == "unstable":   # loose contact: current jumps around
        i_noise = nominal * rng.uniform(0.12, 0.3)
    elif fault == "low_voltage":  # sustained supply problem
        v_mean = rng.uniform(185, 205)

    voltages = rng.normal(v_mean, 1.5, WINDOW)
    currents = np.clip(rng.normal(load, i_noise, WINDOW), 0, None)
    return window_features(voltages, currents)


def make_dataset(nominal, n, fault=None, seed=0):
    rng = np.random.default_rng(seed)
    return np.array([make_window(rng, nominal, fault) for _ in range(n)])


# ---------------- training ----------------
def train(n_normal=3000, n_test=500, seed=42) -> dict:
    """Train one model per appliance on normal data; evaluate on fresh normal + faulty data."""
    models, report = {}, {}
    for k, (name, nominal) in enumerate(APPLIANCE_PROFILES.items()):
        X = make_dataset(nominal, n_normal, seed=seed + k)
        # max_samples=1.0: each tree sees all training windows. With the default (256) the trees
        # gave points far outside the normal range almost the same score as the most extreme normal
        # points, and only ~20% of drift windows were caught. With 1.0 it is ~100% (see report).
        model = IsolationForest(n_estimators=200, max_samples=1.0, contamination=0.01,
                                random_state=seed).fit(X)
        models[name] = model

        # evaluation on data the model has never seen
        def flagged(fault, s):
            return float(np.mean(model.predict(make_dataset(nominal, n_test, fault, seed=s)) == -1))

        report[name] = {
            "normal_flagged_%": round(100 * flagged(None, 1000 + k), 1),        # false alarms
            "drift_detected_%": round(100 * flagged("drift", 2000 + k), 1),
            "unstable_detected_%": round(100 * flagged("unstable", 3000 + k), 1),
            "low_voltage_detected_%": round(100 * flagged("low_voltage", 4000 + k), 1),
        }
    os.makedirs(os.path.dirname(MODEL_PATH), exist_ok=True)
    joblib.dump(models, MODEL_PATH)
    with open(REPORT_PATH, "w") as f:
        json.dump(report, f, indent=2)
    return report


def load_models() -> dict:
    if not os.path.exists(MODEL_PATH):
        print("[ml] no saved model, training on synthetic data...")
        train()
    return joblib.load(MODEL_PATH)


# ---------------- live detector ----------------
class MaintenanceDetector:
    """Keeps a short window per appliance and decides normal / abnormal for each new reading."""

    def __init__(self, models: dict):
        self.models = models
        self.lock = threading.Lock()
        self.readings = {}   # appliance -> deque of (voltage, current)
        self.decisions = {}  # appliance -> deque of True (abnormal) / False (normal)
        self.last = {}       # appliance -> latest status dict

    def update(self, appliance_id: str, voltage: float, current: float) -> dict:
        """Add one reading; return the appliance's status. status['notify'] is True when
        enough recent windows were abnormal to warrant a maintenance notification."""
        with self.lock:
            model = self.models.get(appliance_id)
            if model is None:
                status = {"appliance_id": appliance_id, "status": "no model", "health": None, "notify": False}
                self.last[appliance_id] = status
                return status

            buf = self.readings.setdefault(appliance_id, deque(maxlen=WINDOW))
            buf.append((voltage, current))
            if len(buf) < WINDOW:
                status = {"appliance_id": appliance_id, "status": "learning", "health": None,
                          "notify": False, "readings_needed": WINDOW - len(buf)}
                self.last[appliance_id] = status
                return status

            feats = window_features([v for v, _ in buf], [i for _, i in buf])
            score = float(model.decision_function([feats])[0])   # < 0 means abnormal
            dec = self.decisions.setdefault(appliance_id, deque(maxlen=WINDOW))
            dec.append(score < 0)

            abnormal = sum(dec)
            health = round(100 * (1 - abnormal / len(dec)))
            if abnormal >= NOTIFY_AFTER:
                label = "service needed"
            elif abnormal >= 3:
                label = "watch"
            else:
                label = "ok"
            nominal = APPLIANCE_PROFILES[appliance_id]
            status = {
                "appliance_id": appliance_id, "status": label, "health": health,
                "score": round(score, 4), "abnormal_in_window": abnormal, "window": len(dec),
                "voltage_avg": round(feats[0], 1), "current_avg": round(feats[1], 2),
                "current_std": round(feats[2], 3), "current_normal": nominal,
                "notify": abnormal >= NOTIFY_AFTER,
            }
            self.last[appliance_id] = status
            return status

    def all_status(self) -> list:
        with self.lock:
            return [dict(s) for s in self.last.values()]


def explain(status: dict) -> str:
    """Plain-language maintenance message for a notification."""
    reasons = []
    nominal = status["current_normal"]
    if status["current_avg"] > nominal * 1.15:
        reasons.append(f"drawing {status['current_avg']:.2f} A vs {nominal:.2f} A normal")
    elif status["current_avg"] < nominal * 0.85:
        reasons.append(f"drawing only {status['current_avg']:.2f} A vs {nominal:.2f} A normal")
    if status["current_std"] > nominal * 0.08:
        reasons.append(f"current is unstable (±{status['current_std']:.2f} A)")
    if status["voltage_avg"] < 207 or status["voltage_avg"] > 253:
        reasons.append(f"supply voltage averaging {status['voltage_avg']:.0f} V")
    why = "; ".join(reasons) or "readings no longer match its normal pattern"
    return (f"Maintenance suggested for {status['appliance_id']}: {why} "
            f"({status['abnormal_in_window']}/{status['window']} recent windows abnormal). Schedule an inspection.")


if __name__ == "__main__":
    print("Training Isolation Forest models on synthetic data...")
    result = train()
    print(json.dumps(result, indent=2))
    print(f"Saved model to {MODEL_PATH}")
