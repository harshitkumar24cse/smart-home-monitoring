/*
  Smart Home Monitoring & Maintenance System
  Phase 2 - IoT connectivity (Wi-Fi + MQTT) on top of Phase 1

  Pot 1 (GPIO34) simulates the voltage sensor  : 0 - 250 V
  Pot 2 (GPIO35) simulates the current sensor  : 0 - 10 A
  P (W)    = V * I
  E (kWh) += P * dt / 3,600,000   (dt in ms, measured, not assumed)
*/
#include <Wire.h>
#include <WiFi.h>
#include <PubSubClient.h>
#include <Adafruit_GFX.h>
#include <Adafruit_SSD1306.h>

// ---------- Pins ----------
#define VOLTAGE_PIN 34
#define CURRENT_PIN 35
#define OLED_SDA    21
#define OLED_SCL    22

// ---------- Wi-Fi / MQTT ----------
const char* WIFI_SSID = "Wokwi-GUEST";   // Wokwi's built-in open network
const char* WIFI_PASS = "";
const char* MQTT_HOST = "broker.hivemq.com";
const int   MQTT_PORT = 1883;
// Must match MQTT_TOPIC in backend/main.py. Change it to something unique to you.
const char* MQTT_TOPIC = "harshit-smarthome-7f3a/readings";
const char* APPLIANCE_ID = "heater";
const unsigned long PUBLISH_INTERVAL_MS = 3000;

WiFiClient wifiClient;
PubSubClient mqtt(wifiClient);
unsigned long lastPublish = 0, lastReconnect = 0;

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
  display.println("Home Monitor");
  display.drawLine(0, 9, 127, 9, SSD1306_WHITE);

  display.setCursor(0, 14);
  display.printf("Voltage: %6.1f V\n", voltage);
  display.setCursor(0, 26);
  display.printf("Current: %6.2f A\n", current);
  display.setCursor(0, 38);
  display.printf("Power  : %6.1f W\n", power);
  display.setCursor(0, 50);
  display.printf("Energy : %.5f kWh", energyKWh);
  display.setCursor(104, 0);
  display.print(mqtt.connected() ? "MQ" : (WiFi.status() == WL_CONNECTED ? "WF" : "--"));

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

  Serial.print("Connecting to Wi-Fi");
  WiFi.begin(WIFI_SSID, WIFI_PASS, 6);
  unsigned long t0 = millis();
  while (WiFi.status() != WL_CONNECTED && millis() - t0 < 15000) {
    delay(250);
    Serial.print(".");
  }
  Serial.println(WiFi.status() == WL_CONNECTED ? " connected" : " FAILED (will retry)");
  mqtt.setServer(MQTT_HOST, MQTT_PORT);

  lastSample = millis();
  Serial.println("Smart Home Monitoring - Phase 2 started");
}

void ensureConnected() {
  if (mqtt.connected()) return;
  if (millis() - lastReconnect < 5000) return;   // retry every 5 s
  lastReconnect = millis();
  if (WiFi.status() != WL_CONNECTED) {
    WiFi.begin(WIFI_SSID, WIFI_PASS, 6);
    return;
  }
  String id = "esp32-home-" + String((uint32_t)esp_random(), HEX);
  Serial.print("MQTT connecting... ");
  if (mqtt.connect(id.c_str())) Serial.println("ok");
  else { Serial.print("failed rc="); Serial.println(mqtt.state()); }
}

void publishReading() {
  char payload[200];
  snprintf(payload, sizeof(payload),
    "{\"appliance_id\":\"%s\",\"voltage\":%.1f,\"current\":%.2f,\"power\":%.1f,\"energy_kwh\":%.5f}",
    APPLIANCE_ID, voltage, current, power, energyKWh);
  bool ok = mqtt.publish(MQTT_TOPIC, payload);
  Serial.printf("[MQTT] %s -> %s\n", ok ? "sent" : "FAILED", payload);
}

void loop() {
  ensureConnected();
  mqtt.loop();

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

  if (millis() - lastPublish >= PUBLISH_INTERVAL_MS) {
    lastPublish = millis();
    if (mqtt.connected()) publishReading();
    else Serial.println("[MQTT] not connected, skipping publish");
  }
}
