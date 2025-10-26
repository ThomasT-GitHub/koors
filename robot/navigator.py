#!/usr/bin/env python3
# project/robot/navigator.py
# Beacon-homing walker with obstacle avoidance (FSM), using `controller`.
# Reads RSSI from backend/app.py (/status). Matches prior navigator behavior.

import os
import time
import random
import requests
from typing import Optional

# --- import controller from sibling file ---
try:
    import controller  # project/robot/controller.py
except Exception as e:
    # Fallback: tweak sys.path to include this file's directory
    import sys, pathlib
    HERE = pathlib.Path(__file__).resolve().parent
    if str(HERE) not in sys.path:
        sys.path.insert(0, str(HERE))
    import controller  # retry

# --- Optional ultrasonic support (safe if missing) ---
def _try_get_distance() -> Optional[float]:
    """
    If you later add a backend sensor function (e.g., backend/input.py:get_distance),
    we’ll use it. Otherwise return None to keep FSM RSSI-only.
    """
    try:
        # Lazy import to avoid hard dependency
        from backend.input import get_distance  # type: ignore
        d = get_distance()
        return float(d) if d is not None else None
    except Exception:
        return None

# ========= Config =========
APP_STATUS_URL = os.getenv("APP_STATUS_URL", "http://127.0.0.1:8080/status")
DOG_PORT = os.getenv("DOG_PORT", "/dev/ttyUSB0")

# -------- Tunables --------
RSSI_EMA_ALPHA = 0.35
RSSI_VALID_AGE_S = 2.5
RSSI_MIN_SEEN = -95
RSSI_APPROACH_GOOD = -70

SCAN_TURN_SECS = 0.35
SCAN_SETTLE_MS = 150
SCAN_SECTORS = 10
SCAN_COOLDOWN_S = 6.0

ADVANCE_STEP_S = 0.6
MICRO_PAUSE_S = 0.15

OBSTACLE_NEAR_CM = 45
OBSTACLE_CLEAR_CM = 65
AVOID_TURN_SECS = 0.5
AVOID_STEP_S = 0.8

LOST_TIMEOUT_S = 6.0
LOST_SPIN_SECS = 0.4

GLOBAL_RUN_LIMIT_S = 60 * 10  # 10 minutes

# ========= Controller adapter (adds tiny helpers) =========
class Dog:
    """
    Thin shim over your `controller` so the FSM can call a consistent set of methods.
    """
    def __init__(self):
        self._connected = False

    def connect_dog(self, port: Optional[str] = None, baud: Optional[int] = None) -> bool:
        # controller.connect_dog takes (port), no baud needed
        p = port or DOG_PORT
        try:
            ok = controller.connect_dog(p)
            self._connected = bool(ok)
            return self._connected
        except Exception:
            self._connected = False
            return False

    def is_connected(self) -> bool:
        return self._connected

    def disconnect(self):
        try:
            controller.disconnect()
        finally:
            self._connected = False

    # Movement primitives (your controller already supports these)
    def stop(self):
        if hasattr(controller, "stop"):
            controller.stop()
        else:
            # Fallback to a neutral stance
            if hasattr(controller, "stand"):
                controller.stand()

    def stand(self): controller.stand() if hasattr(controller, "stand") else None
    def sit(self): controller.sit() if hasattr(controller, "sit") else None

    def walk_forward(self, duration: float): controller.walk_forward(duration)
    def walk_backward(self, duration: float): controller.walk_backward(duration)
    def turn_left(self, duration: float): controller.turn_left(duration)
    def turn_right(self, duration: float): controller.turn_right(duration)

dog = Dog()

# ========= BLE status client =========
class BeaconRSSI:
    def __init__(self):
        self.ema: Optional[float] = None
        self.last_seen: float = 0.0
        self.addr: Optional[str] = None
        self.name: Optional[str] = None

    def refresh(self) -> Optional[float]:
        """
        Pull RSSI from /status, update EMA, return EMA if valid.
        Expects backend/app.py to serve {"beacon": {"rssi": int, "last_seen_epoch": float, ...}}
        """
        try:
            r = requests.get(APP_STATUS_URL, timeout=0.5)
            j = r.json()
            b = j.get("beacon") or {}
            rssi = b.get("rssi")
            last_seen_epoch = float(b.get("last_seen_epoch") or 0.0)

            if rssi is None:
                return self.ema

            # Skip stale samples
            if (time.time() - last_seen_epoch) > RSSI_VALID_AGE_S:
                return self.ema

            # EMA
            rr = float(rssi)
            self.ema = rr if self.ema is None else (RSSI_EMA_ALPHA * rr + (1.0 - RSSI_EMA_ALPHA) * self.ema)
            self.last_seen = time.time()
            self.addr = b.get("address")
            self.name = b.get("name")
            return self.ema
        except Exception:
            return self.ema

    def is_recent(self) -> bool:
        return (time.time() - self.last_seen) <= LOST_TIMEOUT_S

# ========= Heading bookkeeping (time-based) =========
class TimedHeading:
    """
    No IMU; integrate timed turns. One revolution ~ SCAN_SECTORS * SCAN_TURN_SECS.
    """
    def __init__(self):
        self.deg = 0.0

    def deg_per_second(self) -> float:
        rev_secs = max(0.1, SCAN_SECTORS * SCAN_TURN_SECS)
        return 360.0 / rev_secs

    def turn_left_t(self, secs: float):
        dog.turn_left(secs)
        self.deg = (self.deg + secs * self.deg_per_second()) % 360.0

    def turn_right_t(self, secs: float):
        dog.turn_right(secs)
        self.deg = (self.deg - secs * self.deg_per_second()) % 360.0

# ========= FSM =========
SEARCH, ALIGN, ADVANCE, AVOID, LOST = "SEARCH", "ALIGN", "ADVANCE", "AVOID", "LOST"

def get_ultrasonic_distance_cm() -> Optional[float]:
    return _try_get_distance()  # None unless you add backend/input.py:get_distance

def get_camera_obstacle() -> bool:
    return False  # stub (add vision later if desired)

class Navigator:
    def __init__(self):
        self.beacon = BeaconRSSI()
        self.hdg = TimedHeading()
        self.state = SEARCH
        self.last_scan_t = 0.0
        self.global_start = time.time()
        self.closest_rssi_seen = -999.0

    def log(self, msg: str):
        print(f"[{self.state}] {msg}")

    def obstacle_ahead(self) -> bool:
        d = get_ultrasonic_distance_cm()
        cam_block = get_camera_obstacle()
        if cam_block:
            return True
        if d is None:
            return False
        return d < OBSTACLE_NEAR_CM

    def path_clear(self) -> bool:
        d = get_ultrasonic_distance_cm()
        if d is None:
            return True
        return d >= OBSTACLE_CLEAR_CM

    def bearing_scan(self) -> Optional[int]:
        self.log("Starting bearing scan…")
        best_idx, best_val = None, -9999.0
        spin_left = random.choice([True, False])

        for i in range(SCAN_SECTORS):
            if spin_left:
                self.hdg.turn_left_t(SCAN_TURN_SECS)
            else:
                self.hdg.turn_right_t(SCAN_TURN_SECS)

            time.sleep(SCAN_SETTLE_MS / 1000.0)
            rssi = self.beacon.refresh()
            if rssi is not None and rssi > best_val:
                best_val = rssi
                best_idx = i

        # Rewind to best sector
        if best_idx is not None:
            steps = (SCAN_SECTORS - 1 - best_idx) if spin_left else (best_idx + 1)
            turn_secs = steps * SCAN_TURN_SECS
            if spin_left:
                self.hdg.turn_right_t(turn_secs)
            else:
                self.hdg.turn_left_t(turn_secs)

        self.last_scan_t = time.time()
        self.log(f"Scan done. Best sector={best_idx} RSSI≈{best_val:.1f} dBm")
        return best_idx

    def step(self):
        # Global backstop
        if GLOBAL_RUN_LIMIT_S and (time.time() - self.global_start) > GLOBAL_RUN_LIMIT_S:
            self.log("Global time limit reached; stopping.")
            dog.stop()
            raise SystemExit

        # Refresh RSSI
        rssi = self.beacon.refresh()
        if rssi is not None:
            self.closest_rssi_seen = max(self.closest_rssi_seen, rssi)

        # --- SEARCH ---
        if self.state == SEARCH:
            if self.beacon.is_recent() and (rssi is not None and rssi > RSSI_MIN_SEEN):
                if (time.time() - self.last_scan_t) > SCAN_COOLDOWN_S:
                    self.bearing_scan()
                self.state = ALIGN
                return

            self.log("No good RSSI; spinning to find beacon…")
            self.hdg.turn_left_t(LOST_SPIN_SECS)
            time.sleep(MICRO_PAUSE_S)
            return

        # --- ALIGN ---
        if self.state == ALIGN:
            if self.obstacle_ahead():
                self.log("Obstacle ahead during ALIGN; switching to AVOID.")
                dog.stop()
                self.state = AVOID
                return

            if rssi is not None and rssi >= RSSI_APPROACH_GOOD:
                self.state = ADVANCE
                return

            if (time.time() - self.last_scan_t) > SCAN_COOLDOWN_S:
                self.bearing_scan()

            if random.random() < 0.5:
                self.hdg.turn_left_t(0.18)
            else:
                self.hdg.turn_right_t(0.18)
            time.sleep(MICRO_PAUSE_S)

            if not self.beacon.is_recent() or (rssi is None or rssi < RSSI_MIN_SEEN):
                self.state = LOST
            return

        # --- ADVANCE ---
        if self.state == ADVANCE:
            if self.obstacle_ahead():
                self.log("Obstacle detected during ADVANCE; switching to AVOID.")
                dog.stop()
                self.state = AVOID
                return

            if not self.beacon.is_recent() or (rssi is None or rssi < RSSI_MIN_SEEN):
                self.log("Lost beacon while advancing.")
                dog.stop()
                self.state = LOST
                return

            step_time = ADVANCE_STEP_S * (0.5 if rssi >= RSSI_APPROACH_GOOD else 1.0)
            dog.walk_forward(step_time)
            time.sleep(MICRO_PAUSE_S)

            rssi_after = self.beacon.refresh() or rssi
            if rssi_after < self.closest_rssi_seen - 1.5:
                if random.random() < 0.5:
                    self.hdg.turn_left_t(0.2)
                else:
                    self.hdg.turn_right_t(0.2)
                time.sleep(MICRO_PAUSE_S)

            if (time.time() - self.last_scan_t) > (SCAN_COOLDOWN_S * 1.5):
                self.bearing_scan()
            return

        # --- AVOID ---
        if self.state == AVOID:
            turn_dir_left = random.random() < 0.5
            self.log(f"Avoiding: turn {'left' if turn_dir_left else 'right'} & step.")
            if turn_dir_left:
                self.hdg.turn_left_t(AVOID_TURN_SECS)
            else:
                self.hdg.turn_right_t(AVOID_TURN_SECS)
            time.sleep(MICRO_PAUSE_S)

            dog.walk_forward(AVOID_STEP_S)
            time.sleep(MICRO_PAUSE_S)
            dog.stop()

            if self.path_clear():
                self.state = ALIGN
            else:
                self.log("Path still blocked; repeating avoid maneuver.")
            return

        # --- LOST ---
        if self.state == LOST:
            self.log("Reacquiring beacon…")
            self.hdg.turn_right_t(LOST_SPIN_SECS)
            time.sleep(MICRO_PAUSE_S)

            if self.beacon.is_recent() and (rssi is not None and rssi > RSSI_MIN_SEEN):
                self.state = SEARCH
            return

    def run(self):
        self.log("Starting navigator. Connecting to dog…")
        if not dog.is_connected():
            if not dog.connect_dog(DOG_PORT):
                print(f"❌ Failed to open port {DOG_PORT}.")
                print("💡 macOS ports look like /dev/tty.usbserial-XXXX or /dev/tty.usbmodem-XXXX")
                print("   Linux/Pi ports look like /dev/ttyUSB0 or /dev/ttyAMA0 (add user to 'dialout').")
                return

        # Neutral posture to start
        dog.stand()
        time.sleep(1.0)
        dog.stop()

        try:
            while True:
                self.step()
        except KeyboardInterrupt:
            print("\n[MAIN] Ctrl-C received. Stopping.")
        finally:
            dog.stop()
            dog.sit()
            dog.disconnect()

if __name__ == "__main__":
    Navigator().run()