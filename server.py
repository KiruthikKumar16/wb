import json
import os
import sys
from datetime import datetime, timezone
import csv
import time
from pathlib import Path

import paho.mqtt.client as mqtt
from dotenv import load_dotenv

try:
	from twilio.rest import Client as TwilioClient  # type: ignore
except Exception:  # pragma: no cover - allows running without Twilio installed
	TwilioClient = None  # type: ignore


def iso_now() -> str:
	return datetime.now(timezone.utc).isoformat()


def load_config() -> dict:
	load_dotenv()
	return {
		"broker_host": os.getenv("BROKER_HOST", "broker.hivemq.com"),
		"broker_port": int(os.getenv("BROKER_PORT", "1883")),
		"topic_sos": os.getenv("TOPIC_SOS", "wearable/+/sos"),
		"topic_status": os.getenv("TOPIC_STATUS", "wearable/+/status"),
		"topic_tamper": os.getenv("TOPIC_TAMPER", "wearable/+/tamper"),
		"twilio_sid": os.getenv("TWILIO_SID", ""),
		"twilio_token": os.getenv("TWILIO_TOKEN", ""),
		"twilio_from": os.getenv("TWILIO_FROM", ""),
		"emergency_numbers": [n.strip() for n in os.getenv("EMERGENCY_NUMBERS", "").split(",") if n.strip()],
		"twilio_enable_calls": os.getenv("TWILIO_ENABLE_CALLS", "false").lower() in ("1", "true", "yes", "on"),
		"twilio_call_message": os.getenv("TWILIO_CALL_MESSAGE", "This is an automated safety alert. Please check on the sender immediately."),
		"rate_limit_seconds": int(os.getenv("RATE_LIMIT_SECONDS", "120")),
		"retry_attempts": int(os.getenv("RETRY_ATTEMPTS", "3")),
	}


class SosServer:
	def __init__(self, config: dict):
		self.broker_host: str = config["broker_host"]
		self.broker_port: int = config["broker_port"]
		self.topic_sos: str = config["topic_sos"]
		self.topic_status: str = config["topic_status"]
		self.topic_tamper: str = config["topic_tamper"]
		self.emergency_numbers: list[str] = config["emergency_numbers"]
		self.rate_limit_seconds: int = config["rate_limit_seconds"]
		self.retry_attempts: int = config["retry_attempts"]

		self.client = mqtt.Client(client_id="wearable-server-sub")
		self.client.on_connect = self._on_connect
		self.client.on_message = self._on_message
		self.client.on_disconnect = self._on_disconnect

		self.twilio = None
		twilio_sid = config["twilio_sid"]
		twilio_token = config["twilio_token"]
		twilio_from = config["twilio_from"]
		self.twilio_from = twilio_from
		self.twilio_enable_calls: bool = config["twilio_enable_calls"]
		self.twilio_call_message: str = config["twilio_call_message"]
		if TwilioClient and twilio_sid and twilio_token and twilio_from:
			self.twilio = TwilioClient(twilio_sid, twilio_token)
			print("[server] Twilio enabled")
		else:
			print("[server] Twilio not configured; SMS will be printed to console")

		# CSV logs
		self.sos_log_path = Path("sos_log.csv")
		self.status_log_path = Path("status_log.csv")
		self._init_csv(self.sos_log_path, ["ts", "deviceId", "lat", "lon", "reason", "mapsUrl"])
		self._init_csv(self.status_log_path, ["ts", "deviceId", "state", "batteryPercent", "lat", "lon"])

		# Rate limiting: (deviceId, number) -> last_ts
		self._rate_map: dict[tuple[str, str], float] = {}

	def _on_connect(self, client, userdata, flags, rc):
		print(f"[server] MQTT connected (rc={rc})")
		client.subscribe(self.topic_sos, qos=1)
		client.subscribe(self.topic_status, qos=0)
		client.subscribe(self.topic_tamper, qos=1)
		print(f"[server] Subscribed: SOS='{self.topic_sos}', STATUS='{self.topic_status}', TAMPER='{self.topic_tamper}'")

	def _on_disconnect(self, client, userdata, rc):
		print(f"[server] MQTT disconnected (rc={rc})")

	def _init_csv(self, path: Path, headers: list[str]) -> None:
		if not path.exists():
			with path.open("w", newline="", encoding="utf-8") as f:
				writer = csv.writer(f)
				writer.writerow(headers)

	def _send_sms(self, body: str) -> None:
		if not self.emergency_numbers:
			print("[server] No EMERGENCY_NUMBERS configured; skipping SMS")
			print(f"[server] (SMS MOCK) {body}")
			return
		if not self.twilio:
			for number in self.emergency_numbers:
				print(f"[server] (SMS MOCK) to {number}: {body}")
			return
		for number in self.emergency_numbers:
			if not self._check_rate_limit("sms", number):
				continue
			self._with_retries(lambda: self._twilio_send_sms(number, body), f"SMS to {number}")

	def _twilio_send_sms(self, number: str, body: str) -> None:
		msg = self.twilio.messages.create(body=body, from_=self.twilio_from, to=number)  # type: ignore
		print(f"[server] SMS sent to {number} sid={msg.sid}")

	def _on_message(self, client, userdata, msg):
		try:
			data = json.loads(msg.payload.decode("utf-8"))
		except Exception as exc:
			print(f"[server] bad payload on {msg.topic}: {exc}")
			return

		topic = msg.topic
		if "/sos" in topic:
			self._handle_sos(data)
		elif "/status" in topic:
			self._handle_status(data)
		elif "/tamper" in topic:
			self._handle_tamper(data)

	def _handle_sos(self, data: dict) -> None:
		device_id = data.get("deviceId", "unknown")
		lat = data.get("lat")
		lon = data.get("lon")
		maps_url = data.get("mapsUrl") or (f"https://maps.google.com/?q={lat},{lon}" if lat and lon else "")
		timestamp = data.get("ts", iso_now())
		reason = data.get("reason", "unknown")
		print(f"[server] SOS from {device_id} at {timestamp} (reason={reason}) → {lat},{lon}")
		# ACK back to device
		ack_topic = f"wearable/{device_id}/ack"
		self.client.publish(ack_topic, json.dumps({"ok": True, "ts": iso_now()}), qos=1, retain=False)
		# Log CSV
		with self.sos_log_path.open("a", newline="", encoding="utf-8") as f:
			writer = csv.writer(f)
			writer.writerow([timestamp, device_id, lat, lon, reason, maps_url])
		# Notify
		message = f"SOS from {device_id} at {timestamp}. Location: {lat},{lon} {maps_url}"
		self._send_sms(message)
		if self.twilio_enable_calls:
			self._send_calls(message)

	def _handle_status(self, data: dict) -> None:
		device_id = data.get("deviceId", "unknown")
		ts = data.get("ts", iso_now())
		state = data.get("state", "unknown")
		batt = data.get("batteryPercent")
		lat = data.get("lat")
		lon = data.get("lon")
		with self.status_log_path.open("a", newline="", encoding="utf-8") as f:
			writer = csv.writer(f)
			writer.writerow([ts, device_id, state, batt, lat, lon])
		# Low battery alert
		try:
			if batt is not None and int(batt) <= 10:
				self._send_sms(f"Low battery alert for {device_id} ({batt}%). Consider charging.")
		except Exception:
			pass

	def _handle_tamper(self, data: dict) -> None:
		device_id = data.get("deviceId", "unknown")
		ts = data.get("ts", iso_now())
		reason = data.get("reason", "unknown")
		print(f"[server] TAMPER from {device_id} at {ts} (reason={reason})")
		self._send_sms(f"Tamper detected on {device_id} at {ts} (reason={reason}).")

	def run(self) -> None:
		self.client.connect(self.broker_host, self.broker_port, keepalive=60)
		self.client.loop_forever()

	def _with_retries(self, func, label: str):
		delay = 1.0
		for attempt in range(1, self.retry_attempts + 1):
			try:
				func()
				return
			except Exception as exc:
				print(f"[server] {label} failed (attempt {attempt}): {exc}")
				if attempt < self.retry_attempts:
					time.sleep(delay)
					delay *= 2

	def _check_rate_limit(self, channel: str, number: str) -> bool:
		# Simple rate limit per number irrespective of device, to avoid spamming
		key = (channel, number)
		now = time.time()
		last = self._rate_map.get(key, 0.0)
		if now - last < self.rate_limit_seconds:
			remain = int(self.rate_limit_seconds - (now - last))
			print(f"[server] Rate limit: skipping {channel} to {number} (wait {remain}s)")
			return False
		self._rate_map[key] = now
		return True

	def _send_calls(self, sms_message: str) -> None:
		if not self.emergency_numbers:
			return
		if not self.twilio:
			for number in self.emergency_numbers:
				print(f"[server] (CALL MOCK) to {number}: {self.twilio_call_message}")
			return
		# Use inline TwiML for TTS
		twiml = f"<Response><Say voice=\"alice\">{self.twilio_call_message}</Say></Response>"
		for number in self.emergency_numbers:
			if not self._check_rate_limit("call", number):
				continue
			self._with_retries(lambda: self._twilio_make_call(number, twiml), f"CALL to {number}")

	def _twilio_make_call(self, number: str, twiml: str) -> None:
		call = self.twilio.calls.create(to=number, from_=self.twilio_from, twiml=twiml)  # type: ignore
		print(f"[server] Call initiated to {number} sid={call.sid}")


def main() -> None:
	config = load_config()
	print(
		f"[server] Starting with broker={config['broker_host']}:{config['broker_port']} "
		f"SOS='{config['topic_sos']}' STATUS='{config['topic_status']}' TAMPER='{config['topic_tamper']}' "
		f"numbers={config['emergency_numbers']}, calls={config['twilio_enable_calls']}"
	)
	server = SosServer(config)
	try:
		server.run()
	except KeyboardInterrupt:
		print("\n[server] Stopped by user")
		sys.exit(0)


if __name__ == "__main__":
	main()


