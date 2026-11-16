"""Send fake readings to the backend over HTTP (no Wokwi needed).

Examples:
  python tools/simulate.py                          # 20 normal readings per appliance
  python tools/simulate.py --count 100 --interval 0.1
  python tools/simulate.py --fault spike --appliances heater
  python tools/simulate.py --fault wear --count 60  # slowly rising, noisy current

Faults:
  none  - normal behaviour
  spike - every 10th reading has a big current spike (over-current)
  sag   - voltage drops to ~190 V (under-voltage)
  wear  - current slowly drifts up and gets noisy (looks like a failing motor)
"""
import argparse
import json
import random
import time
import urllib.request

# Normal current (A) for each simulated appliance. Voltage is ~230 V for all.
NORMAL_CURRENT = {"heater": 5.0, "fridge": 0.8, "ac": 6.5}

parser = argparse.ArgumentParser()
parser.add_argument("--count", type=int, default=20, help="readings per appliance")
parser.add_argument("--url", default="http://127.0.0.1:8000")
parser.add_argument("--appliances", default="heater,fridge,ac")
parser.add_argument("--interval", type=float, default=0.2, help="seconds between rounds")
parser.add_argument("--fault", default="none", choices=["none", "spike", "sag", "wear"])
args = parser.parse_args()

names = args.appliances.split(",")
energy = {name: 0.0 for name in names}

for i in range(args.count):
    for name in names:
        nominal = NORMAL_CURRENT.get(name, 2.0)
        v = random.gauss(230, 2)
        a = random.gauss(nominal, nominal * 0.03)

        if args.fault == "spike" and i % 10 == 9:
            a = nominal * 3
        elif args.fault == "sag":
            v = random.gauss(190, 2)
        elif args.fault == "wear":
            progress = i / max(args.count - 1, 1)          # 0 -> 1
            a = random.gauss(nominal * (1 + 0.4 * progress), nominal * (0.03 + 0.15 * progress))

        a = max(a, 0)
        p = v * a
        energy[name] += p * 3 / 3_600_000  # pretend 3 s between readings (like the ESP32)

        body = json.dumps({"appliance_id": name, "voltage": round(v, 1), "current": round(a, 2),
                           "power": round(p, 1), "energy_kwh": round(energy[name], 5)}).encode()
        req = urllib.request.Request(args.url + "/api/ingest", body,
                                     {"Content-Type": "application/json"})
        print(urllib.request.urlopen(req).read().decode())
    time.sleep(args.interval)
