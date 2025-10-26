#!/usr/bin/env python3
# backend/camera.py
# Pi Camera manager for streaming and future CV processing

import os
import io
import time
import threading
from typing import Optional, Tuple
import numpy as np

# Camera configuration from environment
CAMERA_WIDTH = int(os.getenv("CAMERA_WIDTH", "640"))
CAMERA_HEIGHT = int(os.getenv("CAMERA_HEIGHT", "480"))
CAMERA_FPS = int(os.getenv("CAMERA_FPS", "30"))
CAMERA_ROTATION = int(os.getenv("CAMERA_ROTATION", "0"))  # 0, 90, 180, 270

# Try to import camera libraries
try:
    from picamera2 import Picamera2
    import cv2
    CAMERA_AVAILABLE = True
except ImportError as e:
    print(f"[CAMERA] Warning: Camera libraries not available: {e}")
    print("[CAMERA] Install with: pip install picamera2 opencv-python")
    CAMERA_AVAILABLE = False
    Picamera2 = None
    cv2 = None


class CameraManager:
    """
    Manages Pi Camera capture in a background thread.
    Stores the latest frame for streaming and future CV processing.
    """

    def __init__(self):
        self.camera: Optional[Picamera2] = None
        self.latest_frame: Optional[bytes] = None  # JPEG-encoded frame
        self.latest_array: Optional[np.ndarray] = None  # Raw numpy array for CV
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()

    def start(self) -> bool:
        """Initialize and start camera capture thread."""
        if not CAMERA_AVAILABLE:
            print("[CAMERA] Cannot start: libraries not available")
            return False

        if self._running:
            print("[CAMERA] Already running")
            return True

        try:
            # Initialize picamera2
            self.camera = Picamera2()

            # Configure camera
            config = self.camera.create_preview_configuration(
                main={"size": (CAMERA_WIDTH, CAMERA_HEIGHT), "format": "RGB888"},
                controls={"FrameRate": CAMERA_FPS}
            )
            self.camera.configure(config)

            # Apply rotation if specified
            if CAMERA_ROTATION in [90, 180, 270]:
                self.camera.set_controls({"Rotation": CAMERA_ROTATION})

            # Start camera
            self.camera.start()
            time.sleep(0.5)  # Allow camera to warm up

            # Start capture thread
            self._running = True
            self._thread = threading.Thread(target=self._capture_loop, daemon=True)
            self._thread.start()

            print(f"[CAMERA] Started: {CAMERA_WIDTH}x{CAMERA_HEIGHT} @ {CAMERA_FPS}fps")
            return True

        except Exception as e:
            print(f"[CAMERA] Failed to start: {e}")
            self.camera = None
            return False

    def stop(self):
        """Stop camera capture and cleanup."""
        if not self._running:
            return

        print("[CAMERA] Stopping...")
        self._running = False

        if self._thread:
            self._thread.join(timeout=2.0)

        if self.camera:
            try:
                self.camera.stop()
                self.camera.close()
            except Exception as e:
                print(f"[CAMERA] Error during cleanup: {e}")
            finally:
                self.camera = None

        with self._lock:
            self.latest_frame = None
            self.latest_array = None

        print("[CAMERA] Stopped")

    def _capture_loop(self):
        """Background thread that continuously captures frames."""
        while self._running and self.camera:
            try:
                # Capture frame as numpy array
                frame_array = self.camera.capture_array()

                # Convert RGB to BGR for OpenCV
                frame_bgr = cv2.cvtColor(frame_array, cv2.COLOR_RGB2BGR)

                # Encode as JPEG
                success, jpeg_buffer = cv2.imencode('.jpg', frame_bgr, [cv2.IMWRITE_JPEG_QUALITY, 85])

                if success:
                    with self._lock:
                        self.latest_frame = jpeg_buffer.tobytes()
                        self.latest_array = frame_bgr  # Store for CV processing

            except Exception as e:
                print(f"[CAMERA] Capture error: {e}")
                time.sleep(0.1)

    def get_frame(self) -> Optional[bytes]:
        """Get the latest JPEG-encoded frame."""
        with self._lock:
            return self.latest_frame

    def get_array(self) -> Optional[np.ndarray]:
        """Get the latest frame as numpy array (for CV processing)."""
        with self._lock:
            return self.latest_array.copy() if self.latest_array is not None else None

    def is_running(self) -> bool:
        """Check if camera is running."""
        return self._running and self.camera is not None

    def get_status(self) -> dict:
        """Get camera status information."""
        return {
            "available": CAMERA_AVAILABLE,
            "running": self.is_running(),
            "width": CAMERA_WIDTH,
            "height": CAMERA_HEIGHT,
            "fps": CAMERA_FPS,
            "rotation": CAMERA_ROTATION,
        }


def generate_mjpeg_stream(camera_manager: CameraManager):
    """
    Generator function for MJPEG streaming.
    Yields frames in multipart/x-mixed-replace format for Flask.
    """
    while True:
        frame = camera_manager.get_frame()

        if frame is None:
            # No frame available yet, wait a bit
            time.sleep(0.05)
            continue

        # Yield frame in MJPEG format
        yield (b'--frame\r\n'
               b'Content-Type: image/jpeg\r\n\r\n' + frame + b'\r\n')

        # Control stream rate (prevent overwhelming client)
        time.sleep(1.0 / CAMERA_FPS)
