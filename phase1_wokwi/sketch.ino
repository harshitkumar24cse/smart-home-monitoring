/*
  Smart Home Monitoring & Maintenance System
  Phase 1 - Hardware & Sensor Simulation (Wokwi, ESP32)

  Pot 1 (GPIO34) simulates the voltage sensor  : 0 - 250 V
  Pot 2 (GPIO35) simulates the current sensor  : 0 - 10 A
  P (W)    = V * I
  E (kWh) += P * dt / 3,600,000   (dt in ms, measured, not assumed)
*/
#include <Wire.h>
#include <Adafruit_GFX.h>
#include <Adafruit_SSD1306.h>

// ---------- Pins ----------
#define VOLTAGE_PIN 34
#define CURRENT_PIN 35
#define OLED_SDA    21
#define OLED_SCL    22

// ---------- OLED ----------
#define SCREEN_WIDTH  128
#define SCREEN_HEIGHT 64
#define OLED_ADDR     0x3C
Adafruit_SSD1306 display(SCREEN_WIDTH, SCREEN_HEIGHT, &Wire, -1);

// ---------- Scaling ----------
const float ADC_MAX      = 4095.0;
const float VOLTAGE_MAX  = 250.0;   // V at full-scale
const float CURRENT_MAX  = 10.0;    // A at full-scale
const int   SAMPLES      = 16;      // averaging to reduce ADC noise

// ---------- Timing ----------
const unsigned long SAMPLE_INTERVAL_MS = 1000;
unsigned long lastSample = 0;

// ---------- State ----------
float voltage = 0, current = 0, power = 0;
double energyKWh = 0;

float readAveraged(int pin) {
  long sum = 0;
  for (int i = 0; i < SAMPLES; i++) {
    sum += analogRead(pin);
    delayMicroseconds(200);
  }
  return sum / (float)SAMPLES;
}

void updateDisplay() {
  display.clearDisplay();
  display.setTextSize(1);
  display.setTextColor(SSD1306_WHITE);

  display.setCursor(0, 0);
  display.println("Smart Home Monitor");
  display.drawLine(0, 9, 127, 9, SSD1306_WHITE);

  display.setCursor(0, 14);
  display.printf("Voltage: %6.1f V\n", voltage);
  display.setCursor(0, 26);
  display.printf("Current: %6.2f A\n", current);
  display.setCursor(0, 38);
  display.printf("Power  : %6.1f W\n", power);
  display.setCursor(0, 50);
  display.printf("Energy : %.5f kWh", energyKWh);

  display.display();
}

void setup() {
  Serial.begin(115200);
  analogReadResolution(12);

  Wire.begin(OLED_SDA, OLED_SCL);
  if (!display.begin(SSD1306_SWITCHCAPVCC, OLED_ADDR)) {
    Serial.println("SSD1306 init failed");
    while (true) delay(1000);
  }
  display.clearDisplay();
  display.setTextSize(1);
  display.setTextColor(SSD1306_WHITE);
  display.setCursor(0, 20);
  display.println("Smart Home Monitor");
  display.println("Starting...");
  display.display();
  delay(1000);

  lastSample = millis();
  Serial.println("Smart Home Monitoring - Phase 1 started");
}

void loop() {
  unsigned long now = millis();
  if (now - lastSample < SAMPLE_INTERVAL_MS) return;

  unsigned long dtMs = now - lastSample;   // actual elapsed time
  lastSample = now;

  voltage = readAveraged(VOLTAGE_PIN) / ADC_MAX * VOLTAGE_MAX;
  current = readAveraged(CURRENT_PIN) / ADC_MAX * CURRENT_MAX;
  power   = voltage * current;                       // W
  energyKWh += (double)power * dtMs / 3600000000.0;  // W*ms -> kWh

  updateDisplay();

  Serial.printf("V=%.1f V | I=%.2f A | P=%.1f W | E=%.5f kWh\n",
                voltage, current, power, energyKWh);
  // JSON line - same format Phase 2 will send to the backend
  Serial.printf("{\"appliance_id\":\"heater\",\"voltage\":%.1f,\"current\":%.2f,"
                "\"power\":%.1f,\"energy_kwh\":%.5f}\n",
                voltage, current, power, energyKWh);
}
