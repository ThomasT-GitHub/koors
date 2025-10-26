# app_linux.py
# Flask 3 + Bleak (Linux/BlueZ). Scanner on main thread, Flask in a background thread.
# Adds: /dispatch, /halt, /process_speech endpoints to control navigator and tricks.

import os
import re
import sys
import time
import asyncio
import signal
import threading
import subprocess
import pathlib
from typing import Optional, List, Tuple, Union, Callable
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

# Paths (project layout)
HERE = pathlib.Path(__file__).resolve()
PROJECT_ROOT = HERE.parents[1]  # project/
ROBOT_DIR = PROJECT_ROOT / "robot"
NAVIGATOR_PATH = ROBOT_DIR / "navigator.py"

# Make sure we can import robot/controller.py for process_speech actions
if str(ROBOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROBOT_DIR))
try:
    import controller  # project/robot/controller.py
    _controller_ok = True
except Exception as _e:
    _controller_ok = False

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

# ========== Navigator process management ==========
_nav_lock = threading.Lock()
_nav_proc: Optional[subprocess.Popen] = None

def _proc_alive(p: Optional[subprocess.Popen]) -> bool:
    return p is not None and (p.poll() is None)

def start_navigator() -> dict:
    """Launch project/robot/navigator.py in a background process."""
    global _nav_proc
    with _nav_lock:
        if _proc_alive(_nav_proc):
            return {"ok": True, "status": "already_running", "pid": _nav_proc.pid}
        if not NAVIGATOR_PATH.exists():
            return {"ok": False, "error": f"navigator.py not found at {NAVIGATOR_PATH}"}
        # Inherit env; you can pass DOG_PORT/APP_STATUS_URL via env if needed
        cmd = [sys.executable, str(NAVIGATOR_PATH)]
        try:
            _nav_proc = subprocess.Popen(cmd, cwd=str(ROBOT_DIR))
            return {"ok": True, "status": "dispatched", "pid": _nav_proc.pid}
        except Exception as e:
            return {"ok": False, "error": f"failed_to_start: {e}"}

def stop_navigator(timeout: float = 3.0) -> dict:
    """Stop the running navigator process (if any)."""
    global _nav_proc
    with _nav_lock:
        if not _proc_alive(_nav_proc):
            _nav_proc = None
            return {"ok": True, "status": "not_running"}
        try:
            _nav_proc.terminate()
            t0 = time.time()
            while time.time() - t0 < timeout and _proc_alive(_nav_proc):
                time.sleep(0.05)
            if _proc_alive(_nav_proc):
                _nav_proc.kill()
            pid = _nav_proc.pid
            _nav_proc = None
            return {"ok": True, "status": "stopped", "pid": pid}
        except Exception as e:
            return {"ok": False, "error": f"failed_to_stop: {e}"}

# ========== Flask app ==========
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
            "navigator_running": _proc_alive(_nav_proc),
        },
        "beacon": state.as_dict()
    })


# ---- NEW: dispatch navigator ----
@app.post("/dispatch")
def dispatch():
    """Start the navigator in the background."""
    result = start_navigator()
    code = 200 if result.get("ok") else 500
    return jsonify(result), code

# ---- NEW: halt navigator ----
@app.post("/halt")
def halt():
    """Stop the navigator if running."""
    result = stop_navigator()
    code = 200 if result.get("ok") else 500
    return jsonify(result), code

# ---- NEW: process_speech (override navigation and perform an action) ----
@app.post("/process_speech")
def process_speech():

    if not _controller_ok:
        return jsonify({"ok": False, "error": "controller import failed; ensure project/robot/controller.py is available"}), 500

    body = request.get_json(silent=True) or {}
    action = (body.get("action") or "").strip().lower()
    if not action:
        return jsonify({"ok": False, "error": "missing 'action'"}), 400

    # 1) Override any ongoing navigation
    stop_navigator()

    # 2) Map actions to controller calls
    ACTIONS: dict[str, Callable[[], None]] = {}

    def _cheer():
        # A simple cheer routine using common primitives
        # Fallbacks are safe if some calls don't exist.
        if hasattr(controller, "bark"): controller.bark()
        if hasattr(controller, "wave"): controller.wave()
        if hasattr(controller, "bark"): controller.bark()

    def _call_if(name: str, *args, **kwargs):
        fn = getattr(controller, name, None)
        if callable(fn):
            fn(*args, **kwargs)
            return True
        return False

    ACTIONS["wave"] = lambda: _call_if("wave") or None
    ACTIONS["push_up"] = lambda: _call_if("push_up") or None
    ACTIONS["flip"] = lambda: _call_if("flip") or None
    ACTIONS["cheer"] = _cheer

    if action not in ACTIONS:
        return jsonify({"ok": False, "error": f"unsupported action '{action}'"}), 400

    # 3) Execute the action (connect → act → (optional) disconnect)
    port = os.getenv("DOG_PORT", "/dev/ttyUSB0")
    try:
        if not controller.connect_dog(port):
            return jsonify({"ok": False, "error": f"failed to connect on {port}"}), 500

        # Small prep: stand if available
        if hasattr(controller, "stand"):
            controller.stand()
            time.sleep(0.5)

        ACTIONS[action]()
        # Give typical motions a moment to complete
        time.sleep(2.0)

        # Safe finish
        if hasattr(controller, "sit"): controller.sit()
        if hasattr(controller, "disconnect"): controller.disconnect()
    except Exception as e:
        try:
            if hasattr(controller, "disconnect"):
                controller.disconnect()
        finally:
            return jsonify({"ok": False, "error": f"action_failed: {e}"}), 500

    return jsonify({"ok": True, "action": action, "overrode_navigation": True}), 200

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