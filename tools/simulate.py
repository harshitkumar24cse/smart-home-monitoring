"""Send fake readings to the backend over HTTP (no Wokwi needed).
Usage: python tools/simulate.py [count] [base_url]
"""
import json, random, sys, time, urllib.request

count = int(sys.argv[1]) if len(sys.argv) > 1 else 20
base = sys.argv[2] if len(sys.argv) > 2 else "http://127.0.0.1:8000"
energy = 0.0
for i in range(count):
    v = random.gauss(230, 3)
    a = random.gauss(5, 0.3)
    p = v * a
    energy += p * 2 / 3_600_000
    body = json.dumps({"appliance_id": "heater", "voltage": round(v, 1), "current": round(a, 2),
                       "power": round(p, 1), "energy_kwh": round(energy, 5)}).encode()
    req = urllib.request.Request(base + "/api/ingest", body, {"Content-Type": "application/json"})
    print(urllib.request.urlopen(req).read().decode())
    time.sleep(0.2)
