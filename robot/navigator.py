#!/usr/bin/env python3
# project/robot/navigator.py
# Beacon-homing walker (no full scans) with minimum 5-second walking actions.

import os
import time
import random
import requests
from typing import Optional

# ---- controller import ----
try:
    import controller
except Exception:
    import sys, pathlib
    HERE = pathlib.Path(__file__).resolve().parent
    if str(HERE) not in sys.path:
        sys.path.insert(0, str(HERE))
    import controller

# ---- optional ultrasonic hook ----
def _try_get_distance() -> Optional[float]:
    try:
        from backend.input import get_distance  # type: ignore
        d = get_distance()
        return float(d) if d is not None else None
    except Exception:
        return None

# ========= Config / Tunables =========
APP_STATUS_URL = os.getenv("APP_STATUS_URL", "http://127.0.0.1:8080/status")
DOG_PORT = os.getenv("DOG_PORT", "/dev/ttyUSB0")

# RSSI filtering & thresholds
RSSI_EMA_ALPHA     = 0.35
RSSI_VALID_AGE_S   = 2.5
RSSI_MIN_SEEN      = -95
RSSI_APPROACH_GOOD = -70

# Motion tuning
STEP_MIN_S    = 5.0    # minimum walking time per step (seconds)
STEP_BASE_S   = 5.0    # normal forward step
STEP_NEAR_S   = 5.0    # cautious step near strong RSSI
MICRO_PAUSE   = 0.15
STEER_GAIN    = 0.3    # turn duration

# Obstacle avoidance
OBSTACLE_NEAR_CM  = 45
OBSTACLE_CLEAR_CM = 65
AVOID_TURN_S      = 0.5
AVOID_STEP_S      = 5.0  # also 5s walk when avoiding

# Lost / reacquire
LOST_TIMEOUT_S = 6.0
REACQ_SPIN_S   = 0.4

GLOBAL_RUN_LIMIT_S = 60 * 10

# ========= Controller shim with fallbacks =========
class Dog:
    WALK_FWD_TOKEN   = os.getenv("WALK_FWD_TOKEN",   "kwkF")
    WALK_BACK_TOKEN  = os.getenv("WALK_BACK_TOKEN",  "kwkB")
    TURN_LEFT_TOKEN  = os.getenv("TURN_LEFT_TOKEN",  "kwkL")
    TURN_RIGHT_TOKEN = os.getenv("TURN_RIGHT_TOKEN", "kwkR")
    BALANCE_TOKEN    = os.getenv("BALANCE_TOKEN",    "kbalance")

    def __init__(self):
        self._connected = False

    def connect_dog(self, port: Optional[str] = None, baud: Optional[int] = None) -> bool:
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

    def _send(self, cmd: str):
        if hasattr(controller, "send_raw_command"):
            controller.send_raw_command(cmd)
        elif hasattr(controller, "send_command"):
            controller.send_command(cmd)
        else:
            fn = getattr(controller, cmd, None)
            if callable(fn):
                fn()

    def _pulse(self, cmd: str, burst_s: float, settle_s: float = 0.10):
        self._send(cmd)
        time.sleep(max(0.05, burst_s))
        self._send(self.BALANCE_TOKEN)
        time.sleep(max(0.05, settle_s))

    def stop(self):
        if hasattr(controller, "stop"):
            controller.stop()
        else:
            self._send(self.BALANCE_TOKEN)

    def stand(self):
        if hasattr(controller, "stand"):
            controller.stand()
        else:
            self._send("kup")

    def sit(self):
        if hasattr(controller, "sit"):
            controller.sit()
        else:
            self._send("krest")

    def walk_forward(self, duration: float):
        duration = max(duration, STEP_MIN_S)
        print(f"[WALK] forward {duration:.1f}s")
        if hasattr(controller, "walk_forward"):
            controller.walk_forward(duration)
            return
        t_end = time.time() + duration
        while time.time() < t_end:
            self._pulse(self.WALK_FWD_TOKEN, 0.25, 0.10)

    def walk_backward(self, duration: float):
        duration = max(duration, STEP_MIN_S)
        print(f"[WALK] backward {duration:.1f}s")
        if hasattr(controller, "walk_backward"):
            controller.walk_backward(duration)
            return
        t_end = time.time() + duration
        while time.time() < t_end:
            self._pulse(self.WALK_BACK_TOKEN, 0.25, 0.10)

    def turn_left(self, duration: float):
        print(f"[TURN] left {duration:.1f}s")
        if hasattr(controller, "turn_left"):
            controller.turn_left(duration)
            return
        t_end = time.time() + duration
        while time.time() < t_end:
            self._pulse(self.TURN_LEFT_TOKEN, 0.16, 0.08)

    def turn_right(self, duration: float):
        print(f"[TURN] right {duration:.1f}s")
        if hasattr(controller, "turn_right"):
            controller.turn_right(duration)
            return
        t_end = time.time() + duration
        while time.time() < t_end:
            self._pulse(self.TURN_RIGHT_TOKEN, 0.16, 0.08)

dog = Dog()

# ========= Beacon RSSI client =========
class BeaconRSSI:
    def __init__(self):
        self.ema: Optional[float] = None
        self.last_seen: float = 0.0
    def refresh(self) -> Optional[float]:
        try:
            r = requests.get(APP_STATUS_URL, timeout=0.5)
            j = r.json()
            b = j.get("beacon") or {}
            rssi = b.get("rssi")
            last_seen_epoch = float(b.get("last_seen_epoch") or 0.0)
            if rssi is None: return self.ema
            if (time.time() - last_seen_epoch) > RSSI_VALID_AGE_S: return self.ema
            rr = float(rssi)
            self.ema = rr if self.ema is None else (RSSI_EMA_ALPHA * rr + (1.0 - RSSI_EMA_ALPHA) * self.ema)
            self.last_seen = time.time()
            return self.ema
        except Exception:
            return self.ema
    def is_recent(self) -> bool:
        return (time.time() - self.last_seen) <= LOST_TIMEOUT_S

# ========= Helpers =========
def get_ultrasonic_distance_cm() -> Optional[float]:
    return _try_get_distance()

def obstacle_ahead() -> bool:
    d = get_ultrasonic_distance_cm()
    if d is None or d <= 0:
        return False
    return d < OBSTACLE_NEAR_CM

def path_clear() -> bool:
    d = get_ultrasonic_distance_cm()
    return (d is None) or (d >= OBSTACLE_CLEAR_CM)

# ========= Main loop =========
def run():
    global_start = time.time()
    print(f"[BOOT] Checking beacon at {APP_STATUS_URL}")
    try:
        ping = requests.get(APP_STATUS_URL, timeout=1.0).json().get("beacon", {})
        print(f"[BOOT] rssi={ping.get('rssi')} age={ping.get('age_secs')}")
    except Exception as e:
        print(f"[BOOT] /status unreachable: {e}")

    print("[INIT] Connecting to dog…")
    if not dog.connect_dog(DOG_PORT):
        print(f"❌ Failed to open port {DOG_PORT}")
        return

    dog.stand(); time.sleep(1.0); dog.stop()

    beacon = BeaconRSSI()
    closest_rssi_seen = -999.0

    try:
        while True:
            if GLOBAL_RUN_LIMIT_S and (time.time() - global_start) > GLOBAL_RUN_LIMIT_S:
                print("[SAFE] Global run limit reached.")
                break

            rssi = beacon.refresh()
            if rssi is not None:
                closest_rssi_seen = max(closest_rssi_seen, rssi)

            # Lost? small spin to reacquire
            if (rssi is None) or (not beacon.is_recent()) or (rssi < RSSI_MIN_SEEN):
                print("[HOMING] Weak or lost signal; spinning to reacquire…")
                dog.turn_left(REACQ_SPIN_S)
                time.sleep(MICRO_PAUSE)
                continue

            # Avoid obstacles if any
            if obstacle_ahead():
                print("[AVOID] obstacle ahead → sidestep")
                dog.turn_left(AVOID_TURN_S)
                time.sleep(MICRO_PAUSE)
                dog.walk_forward(AVOID_STEP_S)
                dog.stop()
                continue

            # Stronger RSSI → still 5s (minimum)
            step_time = max(STEP_BASE_S if rssi < RSSI_APPROACH_GOOD else STEP_NEAR_S, STEP_MIN_S)
            print(f"[ADV] rssi={rssi:.1f} → forward {step_time:.1f}s")

            # Move forward
            dog.walk_forward(step_time)
            time.sleep(MICRO_PAUSE)

            rssi_after = beacon.refresh() or rssi
            if rssi_after < closest_rssi_seen - 1.5:
                print(f"[CORR] RSSI dropped ({rssi_after:.1f} vs best {closest_rssi_seen:.1f}) → turning")
                if random.random() < 0.5: dog.turn_left(STEER_GAIN)
                else: dog.turn_right(STEER_GAIN)
                time.sleep(MICRO_PAUSE)

    except KeyboardInterrupt:
        print("\n[MAIN] Ctrl-C received. Stopping.")
    finally:
        dog.stop(); dog.sit(); dog.disconnect()
        print("[DONE] Navigator stopped.")

if __name__ == "__main__":
    run()