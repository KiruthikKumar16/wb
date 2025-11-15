#define TINY_GSM_MODEM_SIM800
#include <TinyGsmClient.h>
#include <HardwareSerial.h>
#include <TinyGPSPlus.h>
/*
  ESP32 + SIM800L (SMS) + GPS (optional) + Button/Vibration + Buzzer
  Sends SMS directly on SOS/tamper. Use this if MQTT/WiFi is not available.
*/

// ======== USER CONFIG ========
const char* PHONE_NUMBERS[] = {"+91XXXXXXXXXX"}; // add more if needed
const int PHONE_COUNT = sizeof(PHONE_NUMBERS) / sizeof(PHONE_NUMBERS[0]);
String DEVICE_ID = "esp32-sim800-01";

// SIM800 on UART1 (assign any free pins)
// SIM800 TX -> ESP32 RX (PIN_SIM800_RX), SIM800 RX -> ESP32 TX (PIN_SIM800_TX)
static const int PIN_SIM800_RX = 26; // ESP32 RX pin
static const int PIN_SIM800_TX = 25; // ESP32 TX pin
// GPS on UART2 (optional)
static const int PIN_GPS_RX = 16; // ESP32 RX (to GPS TX)
static const int PIN_GPS_TX = 17; // ESP32 TX (to GPS RX)

// Inputs/Outputs
static const int PIN_BUTTON = 13;     // SOS button (to GND)
static const int PIN_VIBRATION = 4;   // SW-420 DO
static const int PIN_BUZZER = 27;     // Active buzzer
// ======== END USER CONFIG ========

HardwareSerial ModemSerial(1);
HardwareSerial GPSSerial(2);
TinyGsm modem(ModemSerial);
TinyGPSPlus gps;

int batteryPercent = 96;
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

void modemInit() {
  // Power up sequence depends on your SIM800 breakout (ensure proper 4.0V supply)
  // Here we assume it's already powered and connected.
  if (!modem.restart()) {
    // Try once more
    modem.restart();
  }
  // SMS text mode
  modem.sendAT(GF("+CMGF=1"));
  modem.waitResponse(2000);
}

bool readGPS(double& lat, double& lon) {
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

String buildMessage(const char* kind, const char* reason) {
  double lat = 0, lon = 0;
  bool hasFix = readGPS(lat, lon);
  String msg = "";
  msg += String(kind) + " from " + DEVICE_ID + " (" + String(reason) + "). ";
  if (hasFix) {
    msg += "Location: " + String(lat, 6) + "," + String(lon, 6) + " ";
    msg += "https://maps.google.com/?q=" + String(lat, 6) + "," + String(lon, 6);
  } else {
    msg += "Location unavailable.";
  }
  return msg;
}

void sendSMSAll(const String& body) {
  for (int i = 0; i < PHONE_COUNT; i++) {
    const char* num = PHONE_NUMBERS[i];
    bool ok = modem.sendSMS(num, body);
    if (ok) {
      // short ack beep
      beep(60, 60, 2);
    }
    delay(500);
  }
}

void setup() {
  pinMode(PIN_BUTTON, INPUT_PULLUP);
  pinMode(PIN_VIBRATION, INPUT);
  pinMode(PIN_BUZZER, OUTPUT);
  digitalWrite(PIN_BUZZER, LOW);
  Serial.begin(115200);

  // Start serials
  ModemSerial.begin(9600, SERIAL_8N1, PIN_SIM800_RX, PIN_SIM800_TX);
  GPSSerial.begin(9600, SERIAL_8N1, PIN_GPS_RX, PIN_GPS_TX);
  delay(600);
  modemInit();
}

void loop() {
  // SOS button
  static int lastBtn = HIGH;
  int b = digitalRead(PIN_BUTTON);
  if (b == LOW && lastBtn == HIGH) {
    String msg = buildMessage("SOS", "button");
    sendSMSAll(msg);
  }
  lastBtn = b;

  // Vibration tamper
  int vib = digitalRead(PIN_VIBRATION);
  unsigned long now = millis();
  if (vib == HIGH && (now - lastTamperMs) > tamperCooldownMs) {
    lastTamperMs = now;
    String msg = buildMessage("TAMPER", "vibration");
    sendSMSAll(msg);
  }
}


