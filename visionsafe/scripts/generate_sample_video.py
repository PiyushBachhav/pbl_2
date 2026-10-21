"""
Generate a sample video for demo and testing.

Produces:
  videos/sample.mp4

Can be uploaded via the VisionSafe Web UI (Videos page)
or processed via CLI: python ml/inference.py --input videos/sample.mp4
"""

import sys
from pathlib import Path
import cv2
import numpy as np

BASE_DIR = Path(__file__).resolve().parent.parent
OUTPUT_DIR = BASE_DIR / "videos"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
OUTPUT_PATH = OUTPUT_DIR / "sample.mp4"

WIDTH = 640
HEIGHT = 360
FPS = 20
DURATION_SEC = 5
TOTAL_FRAMES = FPS * DURATION_SEC


def generate_video():
    print(f"Generating sample synthetic video at {OUTPUT_PATH}...")
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    out = cv2.VideoWriter(str(OUTPUT_PATH), fourcc, FPS, (WIDTH, HEIGHT))

    if not out.isOpened():
        # Fallback to avc1 or MJPG
        fourcc = cv2.VideoWriter_fourcc(*"MJPG")
        OUTPUT_PATH_AVI = OUTPUT_DIR / "sample.avi"
        out = cv2.VideoWriter(str(OUTPUT_PATH_AVI), fourcc, FPS, (WIDTH, HEIGHT))
        print(f"Fallback to AVI: {OUTPUT_PATH_AVI}")

    # Colors (BGR)
    COLOR_BG = (35, 30, 25)
    COLOR_ZONE = (45, 45, 180)  # Red-ish
    COLOR_PATH = (50, 70, 50)
    COLOR_TEXT = (220, 220, 220)

    for frame_idx in range(TOTAL_FRAMES):
        frame = np.full((HEIGHT, WIDTH, 3), COLOR_BG, dtype=np.uint8)

        # Floor grid lines
        for y in range(120, HEIGHT, 40):
            cv2.line(frame, (0, y), (WIDTH, y), (50, 45, 40), 1)

        # Restricted danger zone polygon
        zone_pts = np.array([[80, 160], [320, 160], [360, 320], [60, 320]], np.int32)
        cv2.polylines(frame, [zone_pts], isClosed=True, color=COLOR_ZONE, thickness=2)
        cv2.putText(frame, "RESTRICTED FORKLIFT ZONE", (90, 180), cv2.FONT_HERSHEY_SIMPLEX, 0.4, COLOR_ZONE, 1)

        # Safe pedestrian lane
        cv2.rectangle(frame, (400, 120), (580, 340), COLOR_PATH, 1)
        cv2.putText(frame, "PEDESTRIAN SAFE AISLE", (410, 140), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (80, 180, 80), 1)

        # Animated Worker 1 (walking into restricted zone)
        t = frame_idx / TOTAL_FRAMES
        w1_x = int(500 - t * 320)
        w1_y = int(220 + np.sin(t * 10) * 10)
        cv2.rectangle(frame, (w1_x - 15, w1_y - 45), (w1_x + 15, w1_y + 45), (200, 150, 50), 2)
        cv2.putText(frame, "Worker #27", (w1_x - 25, w1_y - 50), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (200, 150, 50), 1)

        # Animated Forklift
        f_x = int(120 + t * 140)
        f_y = 260
        cv2.rectangle(frame, (f_x - 30, f_y - 25), (f_x + 30, f_y + 25), (0, 140, 255), 2)
        cv2.putText(frame, "Forklift #3", (f_x - 30, f_y - 30), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 140, 255), 1)

        # Overhead CCTV telemetry header
        cv2.rectangle(frame, (0, 0), (WIDTH, 30), (15, 12, 10), -1)
        cv2.putText(frame, f"CAM-02 DOCK-4 | FRAME {frame_idx:03d}/{TOTAL_FRAMES} | 2026-10-01", (15, 20), cv2.FONT_HERSHEY_SIMPLEX, 0.45, COLOR_TEXT, 1)

        out.write(frame)

    out.release()
    print(f"[OK] Generated sample video successfully! Total frames: {TOTAL_FRAMES}")


if __name__ == "__main__":
    generate_video()
