# Smart Home Monitoring & Maintenance System

Software-only IoT project (Wokwi ESP32 -> backend -> DB -> dashboard -> alerts -> ML).

## Structure
- `phase1_wokwi/`  ESP32 simulation (sketch.ino, diagram.json, libraries.txt)

## Phase 1: run it
1. Go to https://wokwi.com -> New Project -> ESP32.
2. Replace sketch.ino, diagram.json, libraries.txt with the files in `phase1_wokwi/`.
3. Press Play. Turn pot_v (0-250 V) and pot_i (0-10 A).
4. Check the OLED and Serial Monitor: V, I, P = V*I, and kWh accumulating.

Pins: voltage pot -> GPIO34, current pot -> GPIO35, OLED SDA/SCL -> GPIO21/22.
