#include <WiFi.h>
#include <PubSubClient.h>
#include <TinyGPSPlus.h>
/*
  ESP32 + GPS (NEO-6M/NEO-7M) + Vibration sensor (SW-420) + Buzzer
  Sends heartbeat/status and SOS/tamper to MQTT matching the Python server:
    wearable/{deviceId}/status
    wearable/{deviceId}/sos
    wearable/{deviceId}/tamper
    wearable/{deviceId}/ack   (subscribe; beeps on ACK)
*/

// ======== USER CONFIG ========
const char* WIFI_SSID = "YOUR_WIFI_SSID";
const char* WIFI_PASS = "YOUR_WIFI_PASSWORD";
const char* MQTT_HOST = "broker.hivemq.com";
const uint16_t MQTT_PORT = 1883;
String DEVICE_ID = "esp32-ring-01";

// Pins (adjust if needed)
// GPS on UART2: NEO-6M TX -> ESP32 RX2 (GPIO16), NEO-6M RX -> ESP32 TX2 (GPIO17), GND, VCC(3V3/5V)
static const int PIN_GPS_RX = 16; // ESP32 RX (to GPS TX)
static const int PIN_GPS_TX = 17; // ESP32 TX (to GPS RX)
// Inputs/Outputs
static const int PIN_BUTTON = 13;     // SOS button to GND (INPUT_PULLUP)
static const int PIN_VIBRATION = 4;   // SW-420 digital DO
static const int PIN_BUZZER = 27;     // Active buzzer
// ======== END USER CONFIG ========

WiFiClient wifiClient;
PubSubClient mqtt(wifiClient);

HardwareSerial GPSSerial(2); // UART2
TinyGPSPlus gps;

// Topics
String topicBase = "wearable/" + DEVICE_ID;
String topicStatus = topicBase + "/status";
String topicSos = topicBase + "/sos";
String topicTamper = topicBase + "/tamper";
String topicAck = topicBase + "/ack";

// State
unsigned long lastStatusMs = 0;
const unsigned long statusIntervalMs = 10000;
int batteryPercent = 96;
bool armed = true;
unsigned long lastTamperMs = 0;
const unsigned long tamperCooldownMs = 5000;

void beep(uint16_t onMs, uint16_t offMs, int times) {
  for (int i = 0; i < times; i++) {
    digitalWrite(PIN_BUZZER, HIGH);
    delay(onMs);
    digitalWrite(PIN_BUZZER, LOW);
    if (i + 1 < times) delay(offMs);
  }
}

void connectWiFi() {
  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_PASS);
  while (WiFi.status() != WL_CONNECTED) {
    delay(300);
  }
}

void mqttCallback(char* topic, byte* payload, unsigned int length) {
  String t(topic);
  if (t == topicAck) {
    // ACK from server → short confirmation beeps
    beep(60, 60, 2);
  }
}

void connectMQTT() {
  mqtt.setServer(MQTT_HOST, MQTT_PORT);
  mqtt.setCallback(mqttCallback);
  while (!mqtt.connected()) {
    String cid = String("esp32-") + String(random(0xffff), HEX);
    if (mqtt.connect(cid.c_str())) {
      mqtt.subscribe(topicAck.c_str(), 1);
      break;
    }
    delay(500);
  }
}

bool readGPS(double& lat, double& lon) {
  // Parse incoming GPS bytes
  while (GPSSerial.available()) {
    gps.encode(GPSSerial.read());
  }
  if (gps.location.isUpdated() && gps.location.isValid()) {
    lat = gps.location.lat();
    lon = gps.location.lng();
    return true;
  }
  return false;
}

void publishStatus() {
  double lat = 0, lon = 0;
  bool hasFix = readGPS(lat, lon);
  // Construct minimal JSON
  String payload = "{";
  payload += "\"deviceId\":\"" + DEVICE_ID + "\",";
  payload += "\"state\":\"" + String(armed ? "armed" : "disarmed") + "\",";
  payload += "\"batteryPercent\":" + String(batteryPercent) + ",";
  if (hasFix) {
    payload += "\"lat\":" + String(lat, 6) + ",";
    payload += "\"lon\":" + String(lon, 6);
  } else {
    payload += "\"lat\":null,\"lon\":null";
  }
  payload += "}";
  mqtt.publish(topicStatus.c_str(), payload.c_str(), false);
  // drain a bit
  if (batteryPercent > 5) {
    batteryPercent -= random(0, 2);
  }
}

void publishSOS(const char* reason) {
  if (!armed) return;
  double lat = 0, lon = 0;
  bool hasFix = readGPS(lat, lon);
  String maps = hasFix ? (String("https://maps.google.com/?q=") + String(lat, 6) + "," + String(lon, 6)) : "";
  String payload = "{";
  payload += "\"deviceId\":\"" + DEVICE_ID + "\",";
  payload += "\"type\":\"SOS\",";
  payload += "\"reason\":\"" + String(reason) + "\",";
  payload += "\"batteryPercent\":" + String(batteryPercent) + ",";
  if (hasFix) {
    payload += "\"lat\":" + String(lat, 6) + ",";
    payload += "\"lon\":" + String(lon, 6) + ",";
    payload += "\"mapsUrl\":\"" + maps + "\"";
  } else {
    payload += "\"lat\":null,\"lon\":null";
  }
  payload += "}";
  mqtt.publish(topicSos.c_str(), payload.c_str(), true);
  // alert beep
  beep(180, 120, 2);
}

void publishTamper(const char* reason) {
  String payload = "{";
  payload += "\"deviceId\":\"" + DEVICE_ID + "\",";
  payload += "\"type\":\"TAMPER\",";
  payload += "\"reason\":\"" + String(reason) + "\",";
  payload += "\"batteryPercent\":" + String(batteryPercent);
  payload += "}";
  mqtt.publish(topicTamper.c_str(), payload.c_str(), true);
  beep(60, 60, 4);
}

void setup() {
  pinMode(PIN_BUTTON, INPUT_PULLUP);
  pinMode(PIN_VIBRATION, INPUT);
  pinMode(PIN_BUZZER, OUTPUT);
  digitalWrite(PIN_BUZZER, LOW);

  Serial.begin(115200);
  GPSSerial.begin(9600, SERIAL_8N1, PIN_GPS_RX, PIN_GPS_TX);

  connectWiFi();
  connectMQTT();
}

void loop() {
  if (WiFi.status() != WL_CONNECTED) {
    connectWiFi();
  }
  if (!mqtt.connected()) {
    connectMQTT();
  }
  mqtt.loop();

  // SOS button (active low)
  static int lastBtn = HIGH;
  int b = digitalRead(PIN_BUTTON);
  if (b == LOW && lastBtn == HIGH) {
    // Simple 5s countdown with cancel if button released; for demo, just send immediately:
    publishSOS("button");
  }
  lastBtn = b;

  // Vibration tamper event (debounced/cooldown)
  int vib = digitalRead(PIN_VIBRATION);
  unsigned long now = millis();
  if (vib == HIGH && (now - lastTamperMs) > tamperCooldownMs) {
    lastTamperMs = now;
    publishTamper("vibration");
  }

  // Periodic status
  if (now - lastStatusMs > statusIntervalMs) {
    lastStatusMs = now;
    publishStatus();
  }
}


