#!/usr/bin/env python3
# robot/vision_navigator.py
# Vision-based person-following navigator

import os
import sys
import time
import pathlib
import requests
from typing import Optional

# Add robot directory to path for controller import
HERE = pathlib.Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import controller

# Config
APP_BASE_URL = os.getenv("APP_BASE_URL", "http://127.0.0.1:8080")
DOG_PORT = os.getenv("DOG_PORT", "/dev/ttyUSB0")

# Navigation parameters (simple, no overengineering)
TURN_DURATION = 0.4  # seconds to turn
WALK_DURATION = 2.0  # seconds to walk forward
CHECK_INTERVAL = 0.5  # seconds between frame checks

# Safety
MAX_RUN_TIME = 300  # 5 minutes max


class VisionNavigator:
    """Simple vision-based person follower."""

    def __init__(self):
        self.start_time = time.time()
        self.status = "initializing"

    def get_vision_data(self) -> Optional[dict]:
        """Get person detection data from backend."""
        try:
            response = requests.get(f"{APP_BASE_URL}/vision/detect", timeout=2.0)
            if response.status_code == 200:
                return response.json()
        except Exception as e:
            print(f"[VISION] Failed to get vision data: {e}")
        return None

    def navigate(self):
        """Main navigation loop."""
        # Connect to robot
        if not controller.connect_dog(DOG_PORT):
            print("[VISION] Failed to connect to robot")
            return

        print("[VISION] Connected to robot, starting vision navigation")
        controller.stand()
        time.sleep(0.5)

        try:
            while time.time() - self.start_time < MAX_RUN_TIME:
                # Get vision data
                data = self.get_vision_data()

                if not data or not data.get("ok"):
                    print("[VISION] No vision data, searching...")
                    self.status = "searching"
                    # Spin slowly to search
                    controller.turn_right(0.3)
                    time.sleep(CHECK_INTERVAL)
                    continue

                position = data.get("position", "none")
                distance = data.get("distance", "far")
                has_obstacle = data.get("obstacle", False)

                print(f"[VISION] Person: {position}, Distance: {distance}, Obstacle: {has_obstacle}")

                # No person detected
                if position == "none":
                    self.status = "searching"
                    controller.turn_right(0.3)
                    time.sleep(CHECK_INTERVAL)
                    continue

                # Person is close - arrival!
                if distance == "close":
                    self.status = "arrived"
                    print("[VISION] Arrived! Doing stretch...")
                    controller.stop()
                    time.sleep(0.5)
                    controller.stretch()
                    time.sleep(2.0)
                    controller.sit()
                    break

                # Obstacle detected - avoid
                if has_obstacle:
                    self.status = "avoiding"
                    print("[VISION] Obstacle detected, turning...")
                    controller.turn_left(TURN_DURATION)
                    time.sleep(CHECK_INTERVAL)
                    continue

                # Person detected - navigate
                self.status = "approaching"

                if position == "left":
                    print("[VISION] Turning left to center person...")
                    controller.turn_left(TURN_DURATION)
                elif position == "right":
                    print("[VISION] Turning right to center person...")
                    controller.turn_right(TURN_DURATION)
                else:  # center
                    print("[VISION] Person centered, walking forward...")
                    controller.walk_forward(WALK_DURATION)

                time.sleep(CHECK_INTERVAL)

            print("[VISION] Navigation complete")

        except KeyboardInterrupt:
            print("[VISION] Interrupted by user")
        except Exception as e:
            print(f"[VISION] Error during navigation: {e}")
        finally:
            controller.stop()
            time.sleep(0.5)
            controller.sit()
            controller.disconnect()
            print("[VISION] Navigator stopped")


if __name__ == "__main__":
    nav = VisionNavigator()
    nav.navigate()
