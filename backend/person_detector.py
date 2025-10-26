#!/usr/bin/env python3
# backend/person_detector.py
# Simple OpenCV-based person detection using HOG descriptor

import cv2
import numpy as np
from typing import Optional, Tuple, Literal

PersonPosition = Literal["left", "center", "right", "none"]
PersonDistance = Literal["close", "medium", "far"]


class PersonDetector:
    """Simple person detector using OpenCV's HOG descriptor."""

    def __init__(self):
        # Initialize HOG person detector (pre-trained)
        self.hog = cv2.HOGDescriptor()
        self.hog.setSVMDetector(cv2.HOGDescriptor_getDefaultPeopleDetector())

        # Detection parameters (tuned for speed)
        self.win_stride = (8, 8)
        self.padding = (8, 8)
        self.scale = 1.05

    def detect_person(self, frame: np.ndarray) -> Tuple[PersonPosition, PersonDistance, Optional[Tuple[int, int, int, int]]]:
        """
        Detect person in frame and return position and distance.

        Returns:
            (position, distance, bbox)
            - position: "left", "center", "right", or "none"
            - distance: "close", "medium", "far"
            - bbox: (x, y, w, h) or None
        """
        if frame is None or frame.size == 0:
            return "none", "far", None

        height, width = frame.shape[:2]

        # Run HOG detection
        boxes, weights = self.hog.detectMultiScale(
            frame,
            winStride=self.win_stride,
            padding=self.padding,
            scale=self.scale,
            useMeanshiftGrouping=False
        )

        if len(boxes) == 0:
            return "none", "far", None

        # Find largest detection (closest person)
        areas = [w * h for (x, y, w, h) in boxes]
        idx = np.argmax(areas)
        x, y, w, h = boxes[idx]

        # Determine horizontal position
        center_x = x + w // 2
        frame_center = width // 2
        tolerance = width * 0.2  # 20% tolerance for "center"

        if center_x < frame_center - tolerance:
            position = "left"
        elif center_x > frame_center + tolerance:
            position = "right"
        else:
            position = "center"

        # Determine distance based on bbox size
        person_area = w * h
        frame_area = width * height
        area_ratio = person_area / frame_area

        if area_ratio > 0.25:  # Person fills >25% of frame
            distance = "close"
        elif area_ratio > 0.10:  # Person fills >10% of frame
            distance = "medium"
        else:
            distance = "far"

        return position, distance, (x, y, w, h)

    def check_obstacle(self, frame: np.ndarray) -> bool:
        """
        Simple obstacle detection: check if path ahead is clear.
        Uses edge detection on bottom third of frame.

        Returns:
            True if obstacle detected, False if clear
        """
        if frame is None or frame.size == 0:
            return False

        height, width = frame.shape[:2]

        # Check bottom third of frame (where obstacles would appear)
        roi = frame[int(height * 0.66):, :]

        # Convert to grayscale
        gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)

        # Edge detection
        edges = cv2.Canny(gray, 50, 150)

        # Count edge pixels
        edge_count = np.count_nonzero(edges)
        edge_density = edge_count / (roi.shape[0] * roi.shape[1])

        # If too many edges, assume obstacle
        # Tune this threshold based on your environment
        OBSTACLE_THRESHOLD = 0.15

        return edge_density > OBSTACLE_THRESHOLD
