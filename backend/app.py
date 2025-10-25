# app.py
# Raspberry Pi daemon: BLE beacon scanner + "home toward beacon" navigator + Flask API.

import os, re, time, asyncio, threading
from typing import Optional, List

from flask import Flask, jsonify, request
from bleak import BleakScanner

from petoi_serial import PetoiSerial

# ---------- Config (env) ----------
RAW_UUID            = (os.getenv("TARGET_SERVICE_UUID") or "").strip()
TARGET_NAME_SUBSTR  = (os.getenv("TARGET_NAME_SUBSTR") or "").strip()  # e.g., "Find Me"
SERIAL_PORT         = os.getenv("SERIAL_PORT", "/dev/ttyUSB0")
SERIAL_BAUD         = int(os.getenv("SERIAL_BAUD", "115200"))

# Homing policy
SAMPLE_SECS         = float(os.getenv("SAMPLE_SECS", "1.2"))  # per-heading RSSI dwell
STEP_SECS           = float(os.getenv("STEP_SECS", "0.7"))    # walk burst
TURN_DWELL_SECS     = float(os.getenv("TURN_DWELL_SECS", "0.6"))
FRESH_MAX_AGE       = float(os.getenv("FRESH_MAX_AGE", "3.0"))  # require beacon seen within N sec
PAUSE_SECS          = float(os.getenv("PAUSE_SECS", "0.3"))   # pause between actions
AUTO_STOP_AFTER     = float(os.getenv("AUTO_STOP_AFTER", "0.8"))  # safety stop after any action
RSSI_FLOOR          = int(os.getenv("RSSI_FLOOR", "-95"))     # ignore weaker than this

def expand_uuid(u: str) -> Optional[str]:
    if not u: return None
    s = u.lower()
    if re.fullmatch(r"[0-9a-f]{4}", s):   return f"0000{s}-0000-1000-8000-00805f9b34fb"
    if re.fullmatch(r"[0-9a-f]{8}", s):   return f"{s}-0000-1000-8000-00805f9b34fb"
    if re.fullmatch(r"[0-9a-f]{32}", s):  return f"{s[0:8]}-{s[8:12]}-{s[12:16]}-{s[16:20]}-{s[20:]}"
    return s

TARGET_SERVICE_UUID = expand_uuid(RAW_UUID)

# ---------- Shared state ----------
class BeaconState:
    def __init__(self):
        self.lock = threading.Lock()
        self.addr: Optional[str] = None
        self.name: Optional[str] = None
        self.rssi: Optional[int] = None
        self.seen: Optional[float] = None

    def update(self, addr: str, name: str, rssi: Optional[int]):
        with self.lock:
            self.addr = addr
            self.name = name
            self.rssi = int(rssi) if rssi is not None else None
            self.seen = time.time()

    def snapshot(self):
        with self.lock:
            return dict(
                address=self.addr, name=self.name, rssi=self.rssi,
                last_seen_epoch=self.seen,
                age_secs=(time.time() - self.seen) if self.seen else None,
            )

state = BeaconState()
serial = PetoiSerial(SERIAL_PORT, SERIAL_BAUD)

# ---------- Flask ----------
app = Flask(__name__)

@app.get("/status")
def status():
    return jsonify({
        "ok": True,
        "config": {
            "target_service_uuid": TARGET_SERVICE_UUID,
            "target_name_substr": TARGET_NAME_SUBSTR,
            "serial_port": SERIAL_PORT,
            "sample_secs": SAMPLE_SECS,
            "step_secs": STEP_SECS,
            "turn_dwell_secs": TURN_DWELL_SECS,
        },
        "beacon": state.snapshot(),
        "running": bool(nav and nav.running)
    })

@app.post("/walk")
def walk_once():
    body = request.get_json(silent=True) or {}
    cmd = body.get("cmd")  # optional override: {"cmd":"kturnL"}
    if cmd:
        serial.send(cmd)
    else:
        serial.walk_forward()
        time.sleep(AUTO_STOP_AFTER)
        serial.stop()
    return jsonify({"ok": True, "sent": cmd or "walk_forward()" })

@app.post("/start")
def start_homing():
    if nav and nav.running:
        return jsonify({"ok": True, "msg": "already running"})
    nav.start()
    return jsonify({"ok": True})

@app.post("/stop")
def stop_homing():
    if nav:
        nav.stop()
    serial.stop()
    return jsonify({"ok": True})

# ---------- Homing logic ----------
class Navigator:
    def __init__(self):
        self.running = False
        self.loop = None  # asyncio loop running Bleak + homing
        self.thread = None

    # ---- BLE detection callback ----
    def _on_detect(self, device, adv):
        # Build filters
        name = (adv.local_name or device.name or "")
        uuids: List[str] = [u.lower() for u in (adv.service_uuids or [])]
        hit = False
        if TARGET_SERVICE_UUID:
            hit = TARGET_SERVICE_UUID.lower() in uuids
        elif TARGET_NAME_SUBSTR:
            hit = TARGET_NAME_SUBSTR.lower() in name.lower()
        else:
            hit = True  # no filters -> accept all (not recommended)
        if hit:
            state.update(device.address, name or device.address, device.rssi)

    # ---- homing policy ----
    async def _sample_rssi(self, dwell: float) -> Optional[float]:
        """Average RSSI over a dwell; returns None if no recent reading."""
        end = time.time() + dwell
        vals = []
        while time.time() < end:
            s = state.snapshot()
            if s["rssi"] is not None and s["age_secs"] is not None and s["age_secs"] < 1.0:
                if s["rssi"] >= RSSI_FLOOR:
                    vals.append(s["rssi"])
            await asyncio.sleep(0.1)
        return (sum(vals)/len(vals)) if vals else None

    async def _homing_loop(self, scanner):
        serial.open()
        serial.stand()
        await asyncio.sleep(0.5)

        while self.running:
            # Require a fresh sighting before acting
            snap = state.snapshot()
            if not (snap["rssi"] is not None and snap["age_secs"] is not None and snap["age_secs"] < FRESH_MAX_AGE):
                # No beacon recently: just pause
                await asyncio.sleep(0.5)
                continue

            # --- Probe headings: Forward (baseline), Left, Right ---
            # Baseline (F)
            f_avg = await self._sample_rssi(SAMPLE_SECS)

            # Left
            serial.turn_left(); await asyncio.sleep(TURN_DWELL_SECS)
            l_avg = await self._sample_rssi(SAMPLE_SECS)

            # Back to center, then Right
            serial.turn_right(); await asyncio.sleep(TURN_DWELL_SECS)  # back to center
            serial.turn_right(); await asyncio.sleep(TURN_DWELL_SECS)  # now right
            r_avg = await self._sample_rssi(SAMPLE_SECS)

            # Return to center
            serial.turn_left(); await asyncio.sleep(TURN_DWELL_SECS)

            # Choose best heading by strongest (least negative) RSSI
            scores = { 'F': f_avg, 'L': l_avg, 'R': r_avg }
            best_dir = max((k for k in scores.keys() if scores[k] is not None),
                           key=lambda k: scores[k],
                           default=None)

            # Act
            if best_dir == 'L':
                serial.turn_left(); await asyncio.sleep(TURN_DWELL_SECS)
            elif best_dir == 'R':
                serial.turn_right(); await asyncio.sleep(TURN_DWELL_SECS)
            else:
                pass  # forward is already centered

            # Short forward step, then stop
            serial.walk_forward()
            await asyncio.sleep(STEP_SECS)
            serial.stop()
            await asyncio.sleep(PAUSE_SECS)

    async def _main(self):
        # Prepare Bleak scanner
        kwargs = {}
        if TARGET_SERVICE_UUID:
            kwargs["service_uuids"] = [TARGET_SERVICE_UUID.lower()]
        scanner = BleakScanner(detection_callback=self._on_detect, **kwargs)
        await scanner.start()
        try:
            await self._homing_loop(scanner)
        finally:
            await scanner.stop()
            serial.stop()

    def _run(self):
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
        self.loop.run_until_complete(self._main())

    def start(self):
        if self.running: return
        self.running = True
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()

    def stop(self):
        self.running = False
        # loop will exit after next cycle; also issue a stop for safety
        serial.stop()

nav = Navigator()

# ---------- Main ----------
if __name__ == "__main__":
    # NOTE: on Linux, BLE scan often needs sudo or setcap. See instructions below.
    # Start Flask in foreground; navigator + scanner run in their own thread when /start is called.
    app.run(host="0.0.0.0", port=8080)