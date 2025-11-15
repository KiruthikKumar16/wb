#include <WiFi.h>
#include <PubSubClient.h>

// Wokwi simulator WiFi
const char* WIFI_SSID = "Wokwi-GUEST";
const char* WIFI_PASS = "";

// Public MQTT broker
const char* MQTT_HOST = "broker.hivemq.com";
const uint16_t MQTT_PORT = 1883;

// Device/topic
const char* DEVICE_ID = "wokwi-esp32-01";
String topicStatus = String("wearable/") + DEVICE_ID + "/status";
String topicSos = String("wearable/") + DEVICE_ID + "/sos";

WiFiClient espClient;
PubSubClient mqtt(espClient);

const int BUTTON_PIN = 4;    // adjust if you wire differently in Wokwi
int lastButtonState = HIGH;
unsigned long lastPublish = 0;
int batteryPercent = 95;

void connectWiFi() {
  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_PASS);
  while (WiFi.status() != WL_CONNECTED) {
    delay(300);
  }
}

void connectMQTT() {
  mqtt.setServer(MQTT_HOST, MQTT_PORT);
  while (!mqtt.connected()) {
    String clientId = String("wokwi-sub-") + String(random(0xffff), HEX);
    if (mqtt.connect(clientId.c_str())) {
      break;
    }
    delay(500);
  }
}

void publishStatus() {
  // Simple fake coordinates (Chennai) with small jitter
  float lat = 13.0827 + ((float)random(-200, 200)) * 0.000009;
  float lon = 80.2707 + ((float)random(-200, 200)) * 0.000009;
  String payload = String("{\"deviceId\":\"") + DEVICE_ID + "\","
                   "\"state\":\"armed\","
                   "\"batteryPercent\":" + String(batteryPercent) + ","
                   "\"lat\":" + String(lat, 6) + ","
                   "\"lon\":" + String(lon, 6) + "}";
  mqtt.publish(topicStatus.c_str(), payload.c_str());
  if (batteryPercent > 5) batteryPercent -= random(0, 2);
}

void publishSos() {
  float lat = 13.0827 + ((float)random(-120, 120)) * 0.000009;
  float lon = 80.2707 + ((float)random(-120, 120)) * 0.000009;
  String maps = String("https://maps.google.com/?q=") + String(lat, 6) + "," + String(lon, 6);
  String payload = String("{\"deviceId\":\"") + DEVICE_ID + "\","
                   "\"type\":\"SOS\","
                   "\"reason\":\"button\","
                   "\"batteryPercent\":" + String(batteryPercent) + ","
                   "\"lat\":" + String(lat, 6) + ","
                   "\"lon\":" + String(lon, 6) + ","
                   "\"mapsUrl\":\"" + maps + "\"}";
  mqtt.publish(topicSos.c_str(), payload.c_str());
}

void setup() {
  pinMode(BUTTON_PIN, INPUT_PULLUP);
  connectWiFi();
  connectMQTT();
}

void loop() {
  if (!mqtt.connected()) {
    connectMQTT();
  }
  mqtt.loop();

  // Heartbeat every ~10s
  unsigned long now = millis();
  if (now - lastPublish > 10000) {
    lastPublish = now;
    publishStatus();
  }

  // Edge detection for button press
  int state = digitalRead(BUTTON_PIN);
  if (state == LOW && lastButtonState == HIGH) {
    publishSos();
    delay(20);
  }
  lastButtonState = state;
}


