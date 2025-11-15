import argparse
import json
import random
import threading
import time
import uuid
from datetime import datetime, timezone
from typing import Optional

import paho.mqtt.client as mqtt
import tkinter as tk
from tkinter import ttk


def iso_now() -> str:
	return datetime.now(timezone.utc).isoformat()


def generate_device_id(prefix: str = "gui-ring") -> str:
	return f"{prefix}-{uuid.uuid4().hex[:6]}"


def jitter_location(base_lat: float, base_lon: float, meters: float = 20.0) -> tuple[float, float]:
	meters_to_degrees = 0.000009
	deg = meters * meters_to_degrees
	return (
		base_lat + random.uniform(-deg, deg),
		base_lon + random.uniform(-deg, deg),
	)


class GuiWearableApp:
	def __init__(self, broker: str, port: int, device_id: str, center_lat: float, center_lon: float, hb: int):
		self.broker = broker
		self.port = port
		self.device_id = device_id
		self.center_lat = center_lat
		self.center_lon = center_lon
		self.hb = hb

		self.topic_base = f"wearable/{self.device_id}"
		self.status_topic = f"{self.topic_base}/status"
		self.sos_topic = f"{self.topic_base}/sos"
		self.ack_topic = f"{self.topic_base}/ack"
		self.tamper_topic = f"{self.topic_base}/tamper"

		self.client = mqtt.Client(client_id=f"{self.device_id}-gui")
		self.client.on_connect = self._on_connect
		self.client.on_disconnect = self._on_disconnect
		self.client.on_message = self._on_message

		self.root = tk.Tk()
		self.root.title(f"Wearable Ring Simulator - {self.device_id}")
		self.root.geometry("420x320")
		self.root.resizable(False, False)

		self.is_connected = tk.StringVar(value="Disconnected")
		self.battery_percent = tk.IntVar(value=97)
		self.armed_state = tk.StringVar(value="armed")
		self.location_label = tk.StringVar(value="lat: -, lon: -")
		self.ack_label = tk.StringVar(value="")
		self.countdown_label = tk.StringVar(value="")
		self._countdown_active = False

		self._build_ui()
		self.root.bind("<space>", lambda e: self.handle_sos())

		self._heartbeat_job: Optional[str] = None
		self._connected = False

	def _build_ui(self) -> None:
		frame = ttk.Frame(self.root, padding=16)
		frame.pack(fill="both", expand=True)

		title = ttk.Label(frame, text="Smart Jewelry - Safety Ring", font=("Segoe UI", 14, "bold"))
		title.pack(pady=(0, 8))

		conn = ttk.Label(frame, textvariable=self.is_connected, foreground="#0a84ff")
		conn.pack()

		loc = ttk.Label(frame, textvariable=self.location_label)
		loc.pack(pady=(4, 10))

		battery_label = ttk.Label(frame, text="Battery")
		battery_label.pack(anchor="w")
		self.battery_bar = ttk.Progressbar(frame, orient="horizontal", length=360, mode="determinate", maximum=100, variable=self.battery_percent)
		self.battery_bar.pack(pady=(0, 8))

		btn_frame = ttk.Frame(frame)
		btn_frame.pack(pady=(8, 6))

		self.sos_btn = ttk.Button(btn_frame, text="SEND SOS (Space)", command=self.handle_sos)
		self.sos_btn.grid(row=0, column=0, padx=6)

		self.arm_btn = ttk.Button(btn_frame, text="Toggle Arm", command=self.toggle_arm)
		self.arm_btn.grid(row=0, column=1, padx=6)

		self.tamper_btn = ttk.Button(btn_frame, text="Tamper", command=self.send_tamper)
		self.tamper_btn.grid(row=0, column=2, padx=6)

		self.lowbat_btn = ttk.Button(btn_frame, text="Low Battery", command=self.set_low_battery)
		self.lowbat_btn.grid(row=0, column=3, padx=6)

		self.countdown_lbl = ttk.Label(frame, textvariable=self.countdown_label, foreground="#cc5500")
		self.countdown_lbl.pack(pady=(4, 0))

		self.ack_lbl = ttk.Label(frame, textvariable=self.ack_label, foreground="#22aa22")
		self.ack_lbl.pack(pady=(2, 8))

		self.quit_btn = ttk.Button(frame, text="Quit", command=self.quit)
		self.quit_btn.pack(pady=(10, 0))

		footer = ttk.Label(frame, text="Tip: Press Space bar to send SOS", foreground="#666")
		footer.pack(pady=(8, 0))

	def connect(self) -> None:
		try:
			self.client.connect(self.broker, self.port, keepalive=60)
			self.client.loop_start()
		except Exception as exc:
			self.is_connected.set(f"Connect error: {exc}")

	def _on_connect(self, client, userdata, flags, rc):
		self._connected = True
		self.is_connected.set(f"Connected to {self.broker}:{self.port}")
		self.client.subscribe(self.ack_topic, qos=1)
		self._schedule_heartbeat()

	def _on_disconnect(self, client, userdata, rc):
		self._connected = False
		self.is_connected.set(f"Disconnected (rc={rc})")
		self._cancel_heartbeat()

	def _on_message(self, client, userdata, msg):
		if msg.topic == self.ack_topic:
			try:
				data = json.loads(msg.payload.decode("utf-8"))
			except Exception:
				data = {}
			self.ack_label.set(f"ACK received at {data.get('ts','')}")
			# Clear ack after a short while
			self.root.after(3000, lambda: self.ack_label.set(""))

	def _schedule_heartbeat(self) -> None:
		self._cancel_heartbeat()
		self._heartbeat_job = self.root.after(self.hb * 1000, self._heartbeat)

	def _cancel_heartbeat(self) -> None:
		if self._heartbeat_job:
			try:
				self.root.after_cancel(self._heartbeat_job)
			except Exception:
				pass
			self._heartbeat_job = None

	def _heartbeat(self) -> None:
		if not self._connected:
			return
		lat, lon = jitter_location(self.center_lat, self.center_lon, meters=20)
		self.location_label.set(f"lat: {lat:.6f}, lon: {lon:.6f}")
		payload = {
			"deviceId": self.device_id,
			"ts": iso_now(),
			"state": self.armed_state.get(),
			"batteryPercent": self.battery_percent.get(),
			"lat": round(lat, 6),
			"lon": round(lon, 6),
		}
		self.client.publish(self.status_topic, json.dumps(payload), qos=0, retain=False)
		new_batt = max(5, self.battery_percent.get() - random.choice([0, 0, 1]))
		self.battery_percent.set(new_batt)
		self._schedule_heartbeat()

	def handle_sos(self) -> None:
		if not self._connected:
			self.is_connected.set("Not connected")
			return
		if self.armed_state.get() != "armed":
			self.countdown_label.set("Device is disarmed. Toggle Arm first.")
			self.root.after(2500, lambda: self.countdown_label.set(""))
			return
		if self._countdown_active:
			return
		self._countdown_active = True
		self.sos_btn.config(state="disabled")
		self._start_countdown(5)

	def _start_countdown(self, seconds: int) -> None:
		self._countdown_secs = seconds
		self.countdown_label.set(f"Sending SOS in {self._countdown_secs}s (Cancel?)")
		# Add a temporary cancel button
		self.cancel_btn = ttk.Button(self.root, text="Cancel SOS", command=self._cancel_countdown)
		self.cancel_btn.pack()
		self._tick_countdown()

	def _tick_countdown(self) -> None:
		if not self._countdown_active:
			return
		if self._countdown_secs <= 0:
			self._finish_countdown(send=True)
			return
		self.countdown_label.set(f"Sending SOS in {self._countdown_secs}s (Cancel?)")
		self._countdown_secs -= 1
		self.root.after(1000, self._tick_countdown)

	def _cancel_countdown(self) -> None:
		self._finish_countdown(send=False)

	def _finish_countdown(self, send: bool) -> None:
		self._countdown_active = False
		self.sos_btn.config(state="normal")
		try:
			self.cancel_btn.destroy()
		except Exception:
			pass
		if send:
			lat, lon = jitter_location(self.center_lat, self.center_lon, meters=10)
			self.location_label.set(f"lat: {lat:.6f}, lon: {lon:.6f}")
			payload = {
				"deviceId": self.device_id,
				"ts": iso_now(),
				"type": "SOS",
				"reason": "gui_button_countdown",
				"batteryPercent": self.battery_percent.get(),
				"lat": round(lat, 6),
				"lon": round(lon, 6),
				"mapsUrl": f"https://maps.google.com/?q={lat},{lon}",
			}
			self.client.publish(self.sos_topic, json.dumps(payload), qos=1, retain=False)
			self._flash_button()
			self.countdown_label.set("")
		else:
			self.countdown_label.set("SOS cancelled")
			self.root.after(1500, lambda: self.countdown_label.set(""))

	def _flash_button(self) -> None:
		original = self.sos_btn.cget("text")
		self.sos_btn.config(text="SOS SENT!", state="disabled")
		self.root.after(1500, lambda: self.sos_btn.config(text=original, state="normal"))

	def toggle_arm(self) -> None:
		new_state = "disarmed" if self.armed_state.get() == "armed" else "armed"
		self.armed_state.set(new_state)

	def send_tamper(self) -> None:
		if not self._connected:
			return
		payload = {"deviceId": self.device_id, "ts": iso_now(), "type": "TAMPER", "reason": "gui_button"}
		self.client.publish(self.tamper_topic, json.dumps(payload), qos=1, retain=False)

	def set_low_battery(self) -> None:
		self.battery_percent.set(5)
		self._heartbeat()

	def quit(self) -> None:
		self._cancel_heartbeat()
		try:
			self.client.loop_stop()
			self.client.disconnect()
		except Exception:
			pass
		self.root.destroy()

	def run(self) -> None:
		self.connect()
		self.root.mainloop()


def parse_args() -> argparse.Namespace:
	parser = argparse.ArgumentParser(description="GUI Wearable Simulator")
	parser.add_argument("--broker", default="broker.hivemq.com", help="MQTT broker host")
	parser.add_argument("--port", type=int, default=1883, help="MQTT broker port")
	parser.add_argument("--device-id", default=generate_device_id(), help="Device ID")
	parser.add_argument("--center-lat", type=float, default=13.0827, help="Base latitude (default: Chennai)")
	parser.add_argument("--center-lon", type=float, default=80.2707, help="Base longitude (default: Chennai)")
	parser.add_argument("--hb", type=int, default=10, help="Heartbeat interval seconds")
	return parser.parse_args()


def main() -> None:
	args = parse_args()
	app = GuiWearableApp(
		broker=args.broker,
		port=args.port,
		device_id=args.device_id,
		center_lat=args.center_lat,
		center_lon=args.center_lon,
		hb=args.hb,
	)
	app.run()


if __name__ == "__main__":
	main()


