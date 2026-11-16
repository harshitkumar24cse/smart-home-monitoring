"""
Phase 5 - alert rules (pure functions, no database, easy to test).

1. Threshold alerts: fixed safe limits for voltage, current and power.
2. Z-score anomaly: is this power reading unusually far from the appliance's recent average?
       z = (x - mean) / std        |z| > Z_LIMIT  ->  anomaly
"""
import os
import statistics

# Safe limits (Indian mains is 230 V +/- 10%). Change with environment variables if needed.
THRESHOLDS = {
    "voltage_min": float(os.getenv("VOLTAGE_MIN", "207")),   # 230 V - 10%
    "voltage_max": float(os.getenv("VOLTAGE_MAX", "253")),   # 230 V + 10%
    "current_max": float(os.getenv("CURRENT_MAX", "9.0")),   # A (the Wokwi pot goes up to 10 A)
    "power_max": float(os.getenv("POWER_MAX", "2000")),      # W
}

# 3.5 rather than 3: with normal sensor noise, 3.0 gave the odd false alarm during testing
Z_LIMIT = float(os.getenv("Z_LIMIT", "3.5"))
Z_WINDOW = int(os.getenv("Z_WINDOW", "60"))        # how many recent readings form the baseline
Z_MIN_SAMPLES = 20                                 # don't judge until we have this many


def check_thresholds(voltage: float, current: float, power: float) -> list:
    """Return a list of (kind, severity, message) for every limit that is broken."""
    t = THRESHOLDS
    found = []
    if voltage > t["voltage_max"]:
        found.append(("over_voltage", "critical", f"Voltage {voltage:.1f} V is above {t['voltage_max']:.0f} V"))
    if 1 < voltage < t["voltage_min"]:  # ~0 V means the device is simply off, not a sag
        found.append(("under_voltage", "warning", f"Voltage {voltage:.1f} V is below {t['voltage_min']:.0f} V"))
    if current > t["current_max"]:
        found.append(("over_current", "critical", f"Current {current:.2f} A is above {t['current_max']:.1f} A"))
    if power > t["power_max"]:
        found.append(("over_power", "warning", f"Power {power:.0f} W is above {t['power_max']:.0f} W"))
    return found


def zscore(history: list, x: float):
    """z-score of x against past values. Returns None if there is not enough history."""
    if len(history) < Z_MIN_SAMPLES:
        return None
    mean = statistics.fmean(history)
    std = statistics.pstdev(history)
    # A perfectly flat signal would give std = 0, so use a small floor (1% of the mean, at least 1 W)
    std = max(std, abs(mean) * 0.01, 1.0)
    return (x - mean) / std


def check_zscore(history: list, power: float) -> list:
    z = zscore(history, power)
    if z is None or abs(z) <= Z_LIMIT:
        return []
    direction = "above" if z > 0 else "below"
    mean = statistics.fmean(history)
    return [("power_anomaly", "warning",
             f"Power {power:.0f} W is unusual (z = {z:+.1f}, {direction} recent average {mean:.0f} W)")]
