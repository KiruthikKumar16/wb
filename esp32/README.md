# ESP32 Firmware (real hardware options)

Two ready-to-flash sketches for your modules:

- `esp32_wifi_mqtt_gps_sos.ino`: ESP32 + WiFi + GPS + vibration + buzzer → publishes to MQTT (works with the Python server).
- `esp32_sim800_sms_sos.ino`: ESP32 + SIM800L + GPS + vibration + buzzer → sends SMS directly (no WiFi/MQTT).

Install these Arduino libraries:
- TinyGPSPlus
- PubSubClient (for MQTT, WiFi sketch)
- TinyGSM (for SIM800 sketch)

## Wiring (common parts)
- Button (SOS): one side to `GND`, other to `GPIO13` (internal pull-up).
- Vibration sensor (SW-420): `DO` to `GPIO4`, `VCC` to `3V3`, `GND` to `GND`.
- Buzzer (active): `+` to `GPIO27`, `-` to `GND`.

### GPS (NEO-6M/NEO-7M)
- GPS `TX` → ESP32 `GPIO16` (RX2)
- GPS `RX` → ESP32 `GPIO17` (TX2)
- GPS `VCC` to `3V3` (or module’s rated voltage), `GND` to `GND`.

### SIM800L (only for SMS sketch)
- IMPORTANT: Use a proper 4.0V–4.2V supply with enough current (≥2A peak). Do not power from 3.3V pin.
- SIM800 `TX` → ESP32 `GPIO26` (RX1 in the sketch)
- SIM800 `RX` → ESP32 `GPIO25` (TX1 in the sketch)
- SIM800 `GND` → ESP32 `GND`
- SIM card required; SMS plan enabled.

## Configure and Flash
1) Open the sketch you want in Arduino IDE (or PlatformIO).
2) Set your WiFi SSID/PASS and `DEVICE_ID` in the `.ino` (WiFi sketch).
3) For SMS sketch, set your phone numbers in `PHONE_NUMBERS`.
4) Select your ESP32 board and COM port, then Upload.

## Topics (WiFi MQTT sketch)
- Publishes:
  - `wearable/{deviceId}/status` (state, battery, lat/lon if fix)
  - `wearable/{deviceId}/sos` (reason, battery, lat/lon, mapsUrl)
  - `wearable/{deviceId}/tamper` (reason, battery)
- Subscribes:
  - `wearable/{deviceId}/ack` (beeps twice on ACK)

Use this with the Python `server.py` already included in the repo.

## Notes
- If GPS has no fix, messages send with lat/lon null. Place antenna outdoors or near window.
- SW-420 is very sensitive—adjust the onboard potentiometer to reduce false triggers.
- SIM800 needs a rock-solid power supply; brown-outs cause resets and SMS failures.


