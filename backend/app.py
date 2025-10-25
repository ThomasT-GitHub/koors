# app_linux.py
# Flask 3 + Bleak (Linux/BlueZ). Scanner on main thread, Flask in a background thread.

import os
import re
import time
import asyncio
import threading
from typing import Optional, List, Tuple, Union
from flask import Flask, jsonify, request
from bleak import BleakScanner

# -------- Config via env --------
RAW_UUID = (os.getenv("TARGET_SERVICE_UUID") or "").strip()   # e.g. 1802 or 1234...90AB
TARGET_NAME_SUBSTR = (os.getenv("TARGET_NAME_SUBSTR") or "").strip()  # e.g. "Find Me"
WALK_CMD = os.getenv("WALK_CMD", "kwkF")
STOP_CMD = os.getenv("STOP_CMD", "d")

# Linux/BlueZ specific
ADAPTER = os.getenv("ADAPTER", "hci0")          # e.g., hci0 or hci1
SCANNING_MODE = os.getenv("SCANNING_MODE", "active")  # "active" or "passive"

def expand_uuid(u: str) -> Optional[str]:
    if not u:
        return None
    s = u.lower().replace("-", "")
    if re.fullmatch(r"[0-9a-f]{4}", s):
        return f"0000{s}-0000-1000-8000-00805f9b34fb"
    if re.fullmatch(r"[0-9a-f]{8}", s):
        return f"{s}-0000-1000-8000-00805f9b34fb"
    if re.fullmatch(r"[0-9a-f]{32}", s):
        return f"{s[0:8]}-{s[8:12]}-{s[12:16]}-{s[16:20]}-{s[20:]}"
    return u  # assume already full form

TARGET_SERVICE_UUID = (expand_uuid(RAW_UUID) or "").lower()

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

# -------- Serial stub (replace with your robot link) --------
class PetoiSerialStub:
    def __init__(self): self.opened = True
    def send(self, token: str): print(f"[SERIAL:STUB] send -> {token!r}")

serial = PetoiSerialStub()

# -------- Flask app (in a thread) --------
app = Flask(__name__)

@app.get("/status")
def status():
    return jsonify({
        "ok": True,
        "config": {
            "target_service_uuid": TARGET_SERVICE_UUID or None,
            "target_name_substr": TARGET_NAME_SUBSTR or None,
            "adapter": ADAPTER,
            "scanning_mode": SCANNING_MODE,
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
    # 127.0.0.1 keeps it local; change to 0.0.0.0 if you want LAN access.
    app.run(host="127.0.0.1", port=8080)

# -------- Bleak scanner (Linux-safe) --------
def run_scanner():
    target_uuid = (TARGET_SERVICE_UUID or "").lower()
    name_sub = (TARGET_NAME_SUBSTR or "").lower()

    def normalize(device, adv) -> Tuple[str, str, Optional[int], List[str]]:
        # device may be a BLEDevice OR a string (address) on some Bleak versions
        addr = device if isinstance(device, str) else getattr(device, "address", None) or "(noaddr)"
        # prefer advertised local_name over device.name
        name = getattr(adv, "local_name", None)
        if not name:
            name = device if isinstance(device, str) else getattr(device, "name", None)
        name = str(name or "")
        rssi = getattr(adv, "rssi", None)
        uuids = [u.lower() for u in (getattr(adv, "service_uuids", None) or [])]
        return addr, name, rssi, uuids

    def on_detect(device, adv):
        addr, name, rssi, suuids = normalize(device, adv)

        # Matching rules: if UUID provided, require it; else optional name substring
        has_uuid = bool(target_uuid) and target_uuid in suuids
        has_name = (not name_sub) or (name and name_sub in name.lower())

        if target_uuid:
            if has_uuid:
                state.update(addr, name or addr, rssi)
                print(f"[MATCH] {name or addr}: RSSI={rssi}, UUIDs={suuids}")
        else:
            if has_name:
                state.update(addr, name or addr, rssi)
                print(f"[MATCH] {name or addr}: RSSI={rssi}, UUIDs={suuids}")

    async def main():
        print("[INIT] Starting Flask on background thread…")
        threading.Thread(target=run_flask, daemon=True).start()

        # Pre-filter by UUID at the adapter if we have one
        service_filter = [target_uuid] if target_uuid else None
        print(f"[SCAN] adapter={ADAPTER} mode={SCANNING_MODE} "
              f"uuid={target_uuid or '(none)'} name_sub='{name_sub or '(none)'}'")
        scanner = BleakScanner(
            detection_callback=on_detect,
            adapter=ADAPTER,
            scanning_mode=SCANNING_MODE,
            service_uuids=service_filter
        )
        try:
            await scanner.start()
        except Exception as e:
            print("[ERROR] Failed to start BLE scanner:", repr(e))
            print("Hint: ensure bluetoothd is running, adapter powered, and (optionally) give python cap_net_raw/cap_net_admin.")
            return

        try:
            while True:
                await asyncio.sleep(0.5)
        finally:
            await scanner.stop()

    asyncio.run(main())

if __name__ == "__main__":
    # Tips:
    # - Keep your phone's Virtual Peripheral in the foreground (LightBlue).
    # - If filtering by UUID, make sure RAW_UUID is correct; 16/32-bit get expanded automatically.
    # - Export ADAPTER=hci1 if using a USB dongle.
    run_scanner()