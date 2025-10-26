# navigator.py
# Beacon-homing walker with obstacle avoidance (FSM).
# Requires: app_linux.py running (serving /status), and your command.py on PYTHONPATH.

import time
import math
import random
import requests
from typing import Optional, Tuple
from backend.input import get_distance

# ---- import your serial control helpers ----
# Adjust to your actual module name(s)
import sys, pathlib, os
ROOT = pathlib.Path(__file__).resolve().parents[1]  # project-root
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# Optional: allow a simulator via env var
if os.getenv("DOG_SIM", "0") == "1":
    from robot import command_sim as dog
else:
    from robot import command as dog

APP_STATUS_URL = "http://127.0.0.1:8080/status"

# -------- Tunables (start here) --------
RSSI_EMA_ALPHA = 0.35            # smoothing factor for RSSI stream
RSSI_VALID_AGE_S = 2.5           # max age (s) for RSSI sample to be considered fresh
RSSI_MIN_SEEN = -95              # below this, assume too far/noise
RSSI_APPROACH_GOOD = -70         # "close enough" to slow down / cautious approach

SCAN_TURN_SECS = 0.35            # duration per sector during scan
SCAN_SETTLE_MS = 150             # wait after a turn before sampling RSSI
SCAN_SECTORS = 10                # how many heading samples in a full scan
SCAN_COOLDOWN_S = 6.0            # don’t rescan too often

ADVANCE_STEP_S = 0.6             # forward burst while homing
MICRO_PAUSE_S = 0.15             # short stop between actions (keeps dog stable)

OBSTACLE_NEAR_CM = 45            # stop/avoid if closer than this
OBSTACLE_CLEAR_CM = 65           # treat path as clear above this
AVOID_TURN_SECS = 0.5            # avoid: turn this long
AVOID_STEP_S = 0.8               # avoid: step forward this long before re-eval

LOST_TIMEOUT_S = 6.0             # if no decent RSSI for this long -> LOST state
LOST_SPIN_SECS = 0.4             # quick spin segments to try to reacquire

# Safety backstop to avoid infinite sprinting into something
GLOBAL_RUN_LIMIT_S = 60 * 10     # 10 minutes (set None to disable)

# --------- Sensor hooks (replace later with real HW/vision) ---------
def get_ultrasonic_distance_cm() -> Optional[float]:
    """
    TODO: Wire your HC-SR04 (or similar) here.
    Return: distance in cm, or None if not available.
    For now, return None (no reading). This keeps behavior RSSI-only with stop-gap safety.
    """
    return get_distance()

def get_camera_obstacle() -> bool:
    """
    TODO: Add simple vision gate, e.g., frontal bounding box occupancy or optical flow.
    Return True if obstacle likely ahead (within ~1-2m cone), else False.
    """
    return False

# --------- BLE status client ---------
class BeaconRSSI:
    def __init__(self):
        self.ema: Optional[float] = None
        self.last_seen: float = 0.0
        self.addr: Optional[str] = None
        self.name: Optional[str] = None

    def refresh(self) -> Optional[float]:
        """
        Pull RSSI from /status, update EMA, return current EMA if valid.
        """
        try:
            r = requests.get(APP_STATUS_URL, timeout=0.5)
            j = r.json()
            b = j.get("beacon") or {}
            rssi = b.get("rssi")
            last_seen_epoch = b.get("last_seen_epoch") or 0.0

            if rssi is None:
                return self.ema  # no update

            # Skip stale samples
            if (time.time() - float(last_seen_epoch)) > RSSI_VALID_AGE_S:
                return self.ema

            # Update EMA
            if self.ema is None:
                self.ema = float(rssi)
            else:
                self.ema = RSSI_EMA_ALPHA * float(rssi) + (1.0 - RSSI_EMA_ALPHA) * self.ema

            self.last_seen = time.time()
            self.addr = b.get("address")
            self.name = b.get("name")
            return self.ema
        except Exception:
            return self.ema

    def is_recent(self) -> bool:
        return (time.time() - self.last_seen) <= LOST_TIMEOUT_S

# --------- Heading bookkeeping (time-based) ----------
class TimedHeading:
    """
    We don't have an IMU here; we keep a rough relative heading by integrating timed turns.
    360° corresponds to one full in-place spin time determined by (SCAN_TURN_SECS * SCAN_SECTORS).
    This is coarse but good enough for sector scans & coarse homing.
    """
    def __init__(self):
        self.deg = 0.0

    def turn_left_t(self, secs: float):
        dog.turn_left(duration=secs)
        self.deg += secs * self.deg_per_second()
        self.deg = self.deg % 360.0

    def turn_right_t(self, secs: float):
        dog.turn_right(duration=secs)
        self.deg -= secs * self.deg_per_second()
        self.deg = self.deg % 360.0

    def deg_per_second(self) -> float:
        # Calibrate empirically: one scan revolution ≈ SCAN_SECTORS * SCAN_TURN_SECS
        rev_secs = max(0.1, SCAN_SECTORS * SCAN_TURN_SECS)
        return 360.0 / rev_secs

# --------- FSM States ----------
SEARCH, ALIGN, ADVANCE, AVOID, LOST = "SEARCH", "ALIGN", "ADVANCE", "AVOID", "LOST"

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
            # Without an ultrasonic reading, be conservative near strong RSSI
            return True
        return d >= OBSTACLE_CLEAR_CM

    def bearing_scan(self) -> Optional[int]:
        """
        Spin in-place, sampling RSSI across sectors. Return index of best sector (0..SCAN_SECTORS-1).
        Also recenters heading estimate to that sector (coarse).
        """
        self.log("Starting bearing scan…")
        best_idx = None
        best_val = -9999.0

        # Choose spin direction randomly to avoid bias
        spin_left = random.choice([True, False])

        # Do one full revolution sampling equally spaced sectors
        for i in range(SCAN_SECTORS):
            # turn to next sector
            if spin_left:
                self.hdg.turn_left_t(SCAN_TURN_SECS)
            else:
                self.hdg.turn_right_t(SCAN_TURN_SECS)

            time.sleep(SCAN_SETTLE_MS / 1000.0)

            rssi = self.beacon.refresh()
            if rssi is not None:
                if rssi > best_val:
                    best_val = rssi
                    best_idx = i

        # Rewind roughly back to the best sector heading
        if best_idx is not None:
            # how far to rotate back to the best sector?
            steps = (SCAN_SECTORS - 1 - best_idx) if spin_left else (best_idx + 1)
            # approximate opposite direction small steps to face best
            turn_secs = steps * SCAN_TURN_SECS
            if spin_left:
                self.hdg.turn_right_t(turn_secs)
            else:
                self.hdg.turn_left_t(turn_secs)

        self.last_scan_t = time.time()
        self.log(f"Scan done. Best sector={best_idx} RSSI≈{best_val:.1f} dBm")
        return best_idx

    def step(self):
        # global safety
        if GLOBAL_RUN_LIMIT_S and (time.time() - self.global_start) > GLOBAL_RUN_LIMIT_S:
            self.log("Global time limit reached; stopping.")
            dog.stop()
            raise SystemExit

        # Always refresh beacon EMA
        rssi = self.beacon.refresh()

        # Track closest so far (for simple “are we improving?” checks)
        if rssi is not None:
            self.closest_rssi_seen = max(self.closest_rssi_seen, rssi)

        # State transitions and actions
        if self.state == SEARCH:
            # If we have recent RSSI, jump to ALIGN (or ADVANCE if very strong)
            if self.beacon.is_recent() and (rssi is not None and rssi > RSSI_MIN_SEEN):
                if (time.time() - self.last_scan_t) > SCAN_COOLDOWN_S:
                    self.bearing_scan()
                self.state = ALIGN
                return

            # Otherwise, do small spins to try to reacquire
            self.log("No good RSSI; spinning to find beacon…")
            self.hdg.turn_left_t(LOST_SPIN_SECS)
            time.sleep(MICRO_PAUSE_S)
            return

        if self.state == ALIGN:
            # If obstacle straight ahead, go AVOID first
            if self.obstacle_ahead():
                self.log("Obstacle ahead during ALIGN; switching to AVOID.")
                dog.stop()
                self.state = AVOID
                return

            # If RSSI got strong enough, just ADVANCE cautiously
            if rssi is not None and rssi >= RSSI_APPROACH_GOOD:
                self.state = ADVANCE
                return

            # Otherwise do a quick micro-scan to slightly improve bearing
            if (time.time() - self.last_scan_t) > SCAN_COOLDOWN_S:
                self.bearing_scan()

            # Nudge: tiny turn left/right to “hill-climb” RSSI
            # We don’t know gradient directly; do a tiny random dither then commit if improved next loop.
            if random.random() < 0.5:
                self.hdg.turn_left_t(0.18)
            else:
                self.hdg.turn_right_t(0.18)
            time.sleep(MICRO_PAUSE_S)

            # If we lose signal, go LOST
            if not self.beacon.is_recent() or (rssi is None or rssi < RSSI_MIN_SEEN):
                self.state = LOST
            return

        if self.state == ADVANCE:
            # Immediate safety
            if self.obstacle_ahead():
                self.log("Obstacle detected during ADVANCE; switching to AVOID.")
                dog.stop()
                self.state = AVOID
                return

            # If RSSI vanished or got terrible, re-acquire
            if not self.beacon.is_recent() or (rssi is None or rssi < RSSI_MIN_SEEN):
                self.log("Lost beacon while advancing.")
                dog.stop()
                self.state = LOST
                return

            # If we’re very close (strong RSSI), slow steps
            step_time = ADVANCE_STEP_S * (0.5 if rssi >= RSSI_APPROACH_GOOD else 1.0)

            # Go forward a bit
            dog.walk_forward(step_time)
            time.sleep(MICRO_PAUSE_S)

            # Small corrective turn “hill-climb”: if RSSI didn’t improve, try a tiny steer
            rssi_after = self.beacon.refresh() or rssi
            if rssi_after < self.closest_rssi_seen - 1.5:  # degrade threshold
                if random.random() < 0.5:
                    self.hdg.turn_left_t(0.2)
                else:
                    self.hdg.turn_right_t(0.2)
                time.sleep(MICRO_PAUSE_S)

            # Occasionally rescan to re-center
            if (time.time() - self.last_scan_t) > (SCAN_COOLDOWN_S * 1.5):
                self.bearing_scan()

            return

        if self.state == AVOID:
            # If an obstacle is seen, do a deterministic sidestep:
            # Pick a direction, turn, forward, then return to ALIGN.
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

            # If path looks clear, go ALIGN; else stay in AVOID for another cycle
            if self.path_clear():
                self.state = ALIGN
            else:
                self.log("Path still blocked; repeating avoid maneuver.")
            return

        if self.state == LOST:
            # Rapid small spins to re-acquire; if RSSI comes back, go SEARCH -> ALIGN
            self.log("Reacquiring beacon…")
            self.hdg.turn_right_t(LOST_SPIN_SECS)
            time.sleep(MICRO_PAUSE_S)

            if self.beacon.is_recent() and (rssi is not None and rssi > RSSI_MIN_SEEN):
                self.state = SEARCH
            return

    def run(self):
        self.log("Starting navigator. Connecting to dog…")
        if not dog.is_connected():
            dog.connect_dog("/dev/ttyUSB0", 115200)

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
