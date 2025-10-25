# app_local.py
# Flask 3-compatible. macOS-friendly: Bleak scanner on main thread, Flask in background thread.

import os
import re
import time
import asyncio
import threading
from typing import Optional, List
from flask import Flask, jsonify, request
from bleak import BleakScanner

# -------- Config via env --------
RAW_UUID = (os.getenv("TARGET_SERVICE_UUID") or "").strip()  # e.g. 1802 or 1234...90AB
TARGET_NAME_SUBSTR = (os.getenv("TARGET_NAME_SUBSTR") or "").strip()  # e.g. "Find Me"
WALK_CMD = os.getenv("WALK_CMD", "kwkF")
STOP_CMD = os.getenv("STOP_CMD", "d")

def expand_uuid(u: str) -> Optional[str]:
    if not u:
        return None
    s = u.lower()
    if re.fullmatch(r"[0-9a-f]{4}", s):
        return f"0000{s}-0000-1000-8000-00805f9b34fb"
    if re.fullmatch(r"[0-9a-f]{8}", s):
        return f"{s}-0000-1000-8000-00805f9b34fb"
    if re.fullmatch(r"[0-9a-f]{32}", s):
        return f"{s[0:8]}-{s[8:12]}-{s[12:16]}-{s[16:20]}-{s[20:]}"
    return s

TARGET_SERVICE_UUID = expand_uuid(RAW_UUID)

# -------- Shared state (thread-safe) --------
class BeaconState:
    def __init__(self):
        self._lock = threading.Lock()
        self.last_addr: Optional[str] = None
        self.last_name: Optional[str] = None
        self.last_rssi: Optional[int] = None
        self.last_seen: Optional[float] = None

    def update(self, addr: str, name: str, rssi: Optional[int]):
        with self._lock:
            self.last_addr = addr
            self.last_name = name
            self.last_rssi = int(rssi) if rssi is not None else None
            self.last_seen = time.time()

    def as_dict(self):
        with self._lock:
            return {
                "address": self.last_addr,
                "name": self.last_name,
                "rssi": self.last_rssi,
                "last_seen_epoch": self.last_seen,
                "age_secs": (time.time() - self.last_seen) if self.last_seen else None,
            }

state = BeaconState()

# -------- Serial stub --------
class PetoiSerialStub:
    def __init__(self): self.opened = True
    def send(self, token: str): print(f"[SERIAL:STUB] send -> {token!r}")

serial = PetoiSerialStub()

# -------- Flask app (will run in a thread) --------
app = Flask(__name__)

@app.get("/status")
def status():
    return jsonify({
        "ok": True,
        "config": {
            "target_service_uuid": TARGET_SERVICE_UUID,
            "target_name_substr": TARGET_NAME_SUBSTR,
            "walk_cmd": WALK_CMD,
            "stop_cmd": STOP_CMD,
        },
        "beacon": state.as_dict()
    })

@app.post("/walk")
def walk():
    body = request.get_json(silent=True) or {}
    cmd = (body.get("cmd") or WALK_CMD).strip()
    serial.send(cmd)
    return jsonify({"ok": True, "sent": cmd, "beacon": state.as_dict()})

@app.post("/stop")
def stop():
    serial.send(STOP_CMD)
    return jsonify({"ok": True, "sent": STOP_CMD})

def run_flask():
    app.run(host="127.0.0.1", port=8080)

# -------- Bleak scanner on main thread --------
def run_scanner():
    target_uuid = (TARGET_SERVICE_UUID or "").lower()
    name_sub = (TARGET_NAME_SUBSTR or "").lower()

    def on_detect(device, adv):
        # Build match rules: if UUID given, require it; else, match by name
        suuids: List[str] = [u.lower() for u in (adv.service_uuids or [])]
        name = (adv.local_name or device.name or "")  # prefer advertised local_name
        match_uuid = (bool(target_uuid) and target_uuid in suuids)
        match_name = (bool(name_sub) and name_sub in name.lower())
        if target_uuid:
            if match_uuid:
                state.update(device.address, name or device.address, device.rssi)
                print(f"[MATCH] {name or device.address}: RSSI={device.rssi}, UUIDs={suuids}")
        else:
            # no UUID filter => accept by name if provided
            if not name_sub or match_name:
                state.update(device.address, name or device.address, device.rssi)
                print(f"[MATCH] {name or device.address}: RSSI={device.rssi}, UUIDs={suuids}")

    async def main():
        print("[INIT] Starting Flask in background thread...")
        threading.Thread(target=run_flask, daemon=True).start()

        # If you want Bleak to pre-filter, pass service_uuids=[target_uuid]
        scanner = BleakScanner(detection_callback=on_detect,
                               service_uuids=[target_uuid] if target_uuid else None)
        await scanner.start()
        target_desc = target_uuid if target_uuid else "(no UUID filter)"
        print(f"[SCAN] running; uuid={target_desc}, name contains '{name_sub or '(none)'}'")
        try:
            while True:
                await asyncio.sleep(0.5)
        finally:
            await scanner.stop()

    asyncio.run(main())

if __name__ == "__main__":
    # Tips before running:
    # - System Settings → Privacy & Security → Bluetooth → allow Terminal/IDE
    # - Turn Bluetooth ON; keep iPhone LightBlue in foreground, Advertising
    run_scanner()