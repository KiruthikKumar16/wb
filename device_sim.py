import argparse
import json
import random
import threading
import time
import uuid
from datetime import datetime, timezone
from typing import Optional

import paho.mqtt.client as mqtt

try:
	import msvcrt  # Windows-only, for non-blocking key checks during countdown
	_HAS_MSVCRT = True
except Exception:
	_HAS_MSVCRT = False


def generate_device_id(prefix: str = "sim-ring") -> str:
	unique_suffix = uuid.uuid4().hex[:6]
	return f"{prefix}-{unique_suffix}"


def get_timestamp_iso8601() -> str:
	return datetime.now(timezone.utc).isoformat()


def jitter_location(base_lat: float, base_lon: float, meters: float = 25.0) -> tuple[float, float]:
	meters_to_degrees = 0.000009
	deg = meters * meters_to_degrees
	return (
		base_lat + random.uniform(-deg, deg),
		base_lon + random.uniform(-deg, deg),
	)


class WearableSimulator:
	def __init__(
		self,
		broker_host: str,
		broker_port: int,
		device_id: str,
		center_lat: float,
		center_lon: float,
		heartbeat_seconds: int = 10,
	):
		self.broker_host = broker_host
		self.broker_port = broker_port
		self.device_id = device_id
		self.center_lat = center_lat
		self.center_lon = center_lon
		self.heartbeat_seconds = heartbeat_seconds

		self.topic_base = f"wearable/{self.device_id}"
		self.status_topic = f"{self.topic_base}/status"
		self.sos_topic = f"{self.topic_base}/sos"
		self.ack_topic = f"{self.topic_base}/ack"
		self.tamper_topic = f"{self.topic_base}/tamper"

		self.client = mqtt.Client(client_id=f"{self.device_id}-pubsub")
		self.client.on_connect = self._on_connect
		self.client.on_disconnect = self._on_disconnect
		self.client.on_message = self._on_message

		self._running = False
		self._battery_percent = 98
		self._armed = True
		self._last_ack: Optional[str] = None
		self._heartbeat_thread: threading.Thread | None = None

	def _on_connect(self, client, userdata, flags, rc):
		print(f"[device] MQTT connected (rc={rc}) as {self.device_id}")
		client.subscribe(self.ack_topic, qos=1)

	def _on_disconnect(self, client, userdata, rc):
		print(f"[device] MQTT disconnected (rc={rc})")

	def _on_message(self, client, userdata, msg):
		if msg.topic == self.ack_topic:
			try:
				data = json.loads(msg.payload.decode("utf-8"))
			except Exception:
				data = {"raw": msg.payload.decode("utf-8", errors="ignore")}
			self._last_ack = data.get("ts") or get_timestamp_iso8601()
			print(f"[device] ACK received: {data}")

	def connect(self) -> None:
		self.client.connect(self.broker_host, self.broker_port, keepalive=60)
		self.client.loop_start()

	def disconnect(self) -> None:
		self.client.loop_stop()
		self.client.disconnect()

	def start(self) -> None:
		if self._running:
			return
		self._running = True
		self.connect()
		self._heartbeat_thread = threading.Thread(target=self._heartbeat_loop, daemon=True)
		self._heartbeat_thread.start()
		print("\nCommands: 's' = SOS, 'q' = quit\n")

	def stop(self) -> None:
		self._running = False
		if self._heartbeat_thread and self._heartbeat_thread.is_alive():
			self._heartbeat_thread.join(timeout=1.0)
		self.disconnect()
		print("[device] stopped")

	def _heartbeat_loop(self) -> None:
		while self._running:
			lat, lon = jitter_location(self.center_lat, self.center_lon, meters=25)
			payload = {
				"deviceId": self.device_id,
				"ts": get_timestamp_iso8601(),
				"state": "armed",
				"batteryPercent": self._battery_percent,
				"lat": round(lat, 6),
				"lon": round(lon, 6),
			}
			self.client.publish(self.status_topic, json.dumps(payload), qos=0, retain=False)
			print(f"[device] status → {payload}")
			self._battery_percent = max(5, self._battery_percent - random.choice([0, 0, 1]))
			time.sleep(self.heartbeat_seconds)

	def _send_status(self) -> None:
		lat, lon = jitter_location(self.center_lat, self.center_lon, meters=25)
		payload = {
			"deviceId": self.device_id,
			"ts": get_timestamp_iso8601(),
			"state": "armed" if self._armed else "disarmed",
			"batteryPercent": self._battery_percent,
			"lat": round(lat, 6),
			"lon": round(lon, 6),
		}
		self.client.publish(self.status_topic, json.dumps(payload), qos=0, retain=False)
		print(f"[device] status → {payload}")

	def send_sos(self, reason: str = "double_tap") -> None:
		if not self._armed:
			print("[device] Ignored SOS: device is disarmed. Press 'a' to arm.")
			return
		lat, lon = jitter_location(self.center_lat, self.center_lon, meters=10)
		payload = {
			"deviceId": self.device_id,
			"ts": get_timestamp_iso8601(),
			"type": "SOS",
			"reason": reason,
			"batteryPercent": self._battery_percent,
			"lat": round(lat, 6),
			"lon": round(lon, 6),
			"mapsUrl": f"https://maps.google.com/?q={lat},{lon}",
		}
		self.client.publish(self.sos_topic, json.dumps(payload), qos=1, retain=False)
		print(f"[device] SOS sent → {payload}")

	def send_tamper(self) -> None:
		payload = {
			"deviceId": self.device_id,
			"ts": get_timestamp_iso8601(),
			"type": "TAMPER",
			"reason": "case_open",
			"batteryPercent": self._battery_percent,
		}
		self.client.publish(self.tamper_topic, json.dumps(payload), qos=1, retain=False)
		print(f"[device] Tamper event → {payload}")

	def set_low_battery(self) -> None:
		self._battery_percent = 5
		print("[device] Battery set to low (5%). Sending status.")
		self._send_status()

	def toggle_arm(self) -> None:
		self._armed = not self._armed
		state = "armed" if self._armed else "disarmed"
		print(f"[device] Device now {state}.")
		self._send_status()

	def sos_with_countdown(self, seconds: int = 5) -> None:
		if not self._armed:
			print("[device] Ignored: device is disarmed. Press 'a' to arm.")
			return
		print(f"[device] SOS arming. Sending in {seconds}s. Press 'c' to cancel.")
		cancelled = False
		start = time.time()
		while time.time() - start < seconds:
			remaining = seconds - int(time.time() - start)
			print(f"  {remaining}...", end="\r", flush=True)
			time.sleep(0.2)
			if _HAS_MSVCRT and msvcrt.kbhit():
				ch = msvcrt.getwch().lower()
				if ch == "c":
					cancelled = True
					break
		print(" " * 20, end="\r")
		if cancelled:
			print("[device] SOS cancelled.")
			return
		self.send_sos(reason="countdown_confirmed")


def parse_args() -> argparse.Namespace:
	parser = argparse.ArgumentParser(description="Wearable safety device simulator (MQTT)")
	parser.add_argument("--broker", default="broker.hivemq.com", help="MQTT broker host")
	parser.add_argument("--port", type=int, default=1883, help="MQTT broker port")
	parser.add_argument("--device-id", default=generate_device_id(), help="Device ID (topic segment)")
	parser.add_argument("--center-lat", type=float, default=13.0827, help="Base latitude (default: Chennai)")
	parser.add_argument("--center-lon", type=float, default=80.2707, help="Base longitude (default: Chennai)")
	parser.add_argument("--hb", type=int, default=10, help="Heartbeat interval seconds")
	return parser.parse_args()


def main() -> None:
	args = parse_args()
	sim = WearableSimulator(
		broker_host=args.broker,
		broker_port=args.port,
		device_id=args.device_id,
		center_lat=args.center_lat,
		center_lon=args.center_lon,
		heartbeat_seconds=args.hb,
	)
	try:
		sim.start()
		print("Commands: s=SOS (countdown), a=arm/disarm, t=tamper, l=low battery, h=help, q=quit")
		while True:
			cmd = input().strip().lower()
			if cmd == "s":
				sim.sos_with_countdown(5)
			elif cmd == "q":
				break
			elif cmd == "a":
				sim.toggle_arm()
			elif cmd == "t":
				sim.send_tamper()
			elif cmd == "l":
				sim.set_low_battery()
			elif cmd == "h":
				print("s=SOS (countdown), a=arm/disarm, t=tamper, l=low battery, h=help, q=quit")
	except KeyboardInterrupt:
		pass
	finally:
		sim.stop()


if __name__ == "__main__":
	main()


