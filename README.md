# Smart Jewelry for Women's Safety (Simulated Hardware - MQTT)

This project simulates a wearable safety device (smart ring/pendant) using software only:
- A "device" publishes status and SOS events over MQTT.
- A "server" listens for SOS and sends SMS alerts (Twilio) or prints to console.
- An optional GUI app gives you a big SOS button and battery indicator.
- An optional Wokwi ESP32 sketch can publish the same MQTT SOS without real hardware.
- Optional real hardware firmware is provided under `esp32/` for ESP32 + GPS + vibration + buzzer (WiFi MQTT or SIM800 SMS).

No custom electronics are required, and this demonstrates a realistic IoT hardware workflow end-to-end.

## Architecture
- Device simulator (Python) → MQTT broker (`broker.hivemq.com`) → Server (Python) → SMS (Twilio)
- Topics:
  - `wearable/{deviceId}/status` (heartbeat with battery, location)
  - `wearable/{deviceId}/sos` (SOS event with location + reason)
  - `wearable/{deviceId}/tamper` (tamper/case-open event)
  - `wearable/{deviceId}/ack` (server acknowledgement back to device)
- Server subscribes to `wearable/+/sos` by default.

## Features
- Countdown with cancel (CLI and GUI) before SOS is sent
- ACKs from server → device via MQTT
- Tamper and low-battery events with alerts
- Server CSV logs: `sos_log.csv`, `status_log.csv`
- Twilio SMS; optional Twilio voice call escalation (TTS)
- Retries with exponential backoff; per-number rate limiting

## Prerequisites
- Python 3.10+ installed
- Internet access (MQTT to `broker.hivemq.com`, optional Twilio HTTPS)
- Windows: run from PowerShell or CMD

## Setup
1) Create and activate a virtual environment (optional but recommended)
```
python -m venv .venv
.venv\Scripts\activate
```

2) Install dependencies
```
pip install -r requirements.txt
```

3) Configure environment (optional for real SMS)
- Copy `env.example` to `.env` and fill values (Twilio trial works with verified numbers).
  - `TWILIO_SID`, `TWILIO_TOKEN`, `TWILIO_FROM`
  - `EMERGENCY_NUMBERS` as comma-separated numbers with country code
- If `.env` is missing or empty, the server prints SMS to console instead of sending.

## Run the server (receiver)
In one terminal:
```
python server.py
```
You should see:
```
[server] Starting with broker=broker.hivemq.com:1883 SOS='wearable/+/sos' STATUS='wearable/+/status' TAMPER='wearable/+/tamper' numbers=[], calls=False
[server] Twilio not configured; SMS will be printed to console
[server] MQTT connected (rc=0)
[server] Subscribed: SOS='wearable/+/sos', STATUS='wearable/+/status', TAMPER='wearable/+/tamper'
```

## Run a device (CLI)
In another terminal:
```
python device_sim.py
```
Commands:
- `s` → SOS with 5s countdown (press `c` during countdown to cancel on Windows)
- `a` → arm/disarm toggle
- `t` → send tamper event
- `l` → set low battery and send status
- `q` → quit

Optional arguments:
```
python device_sim.py --device-id myring-01 --center-lat 13.0827 --center-lon 80.2707 --hb 8
```

## Run the GUI wearable (optional)
```
python gui_ring.py
```
- Press "SEND SOS" or Space → 5s countdown with Cancel button
- Toggle Arm, send Tamper, set Low Battery
- ACKs appear below as “ACK received …”
- The app publishes heartbeat every few seconds and drains battery slowly.

## Wokwi ESP32 (optional, no real board)
- Open `wokwi/sos_mqtt.ino` on `https://wokwi.com` and run the sketch.
- It publishes an SOS to the same MQTT broker when the simulated button is pressed.
- The Python server will receive it as well.

## Real hardware (ESP32)
- See `esp32/`:
  - `esp32_wifi_mqtt_gps_sos.ino` (WiFi + MQTT, works with this server)
  - `esp32_sim800_sms_sos.ino` (direct SMS via SIM800L)
- Wiring and details are in `esp32/README.md`.

## Demo script (suggested)
1) Start `server.py` (shows subscription and Twilio status).
2) Start `gui_ring.py` or `device_sim.py` (shows heartbeats).
3) Trigger SOS (button or press `s` in CLI).
4) Show server terminal receiving SOS; if Twilio configured, show SMS on your phone.
5) Briefly explain that this simulates a BLE/cellular wearable → MQTT → action pipeline.

## Troubleshooting
- MQTT blocked: Some networks block MQTT (1883). Try a mobile hotspot.
- Twilio trial: You must verify destination numbers in Twilio trial. Production numbers can send to any number.
- Tkinter missing: On some Python installs, Tkinter might be excluded. Use the CLI simulator (`device_sim.py`) instead.
- Slow SMS: Cloud SMS can be delayed; for demo, rely on console output if needed.

## Notes
- Public MQTT is for demos only; do not send sensitive data.
- This project is a software stand-in for real hardware and can be ported to ESP32/Pico W later with minimal effort.


