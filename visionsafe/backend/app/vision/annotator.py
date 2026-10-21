"""
Frame annotation utilities for visualization and evidence generation.

These functions draw bounding boxes, track IDs, zone overlays,
PPE status indicators, and event labels on video frames.

Used for:
  1. Annotated output video (demo/testing)
  2. Evidence frame snapshots saved when safety events are created
"""

from __future__ import annotations

import logging
from typing import Optional

import cv2
import numpy as np

from app.vision.detections import TrackedObject, PPEState

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────
# Color palette (BGR)
# ─────────────────────────────────────────
COLORS = {
    "person":    (50,  205, 50),   # lime green
    "helmet":    (0,   255, 255),  # yellow
    "vest":      (0,   165, 255),  # orange
    "forklift":  (0,   0,   255),  # red
    "default":   (200, 200, 200),  # grey
}

SEVERITY_COLORS = {
    "LOW":      (0,   255, 0),    # green
    "MEDIUM":   (0,   165, 255),  # orange
    "HIGH":     (0,   69,  255),  # deep orange
    "CRITICAL": (0,   0,   255),  # red
}

ZONE_ALPHA = 0.25  # Zone fill transparency


def draw_tracked_objects(
    frame: np.ndarray,
    tracked: list[TrackedObject],
    ppe_states: Optional[dict[int, PPEState]] = None,
) -> np.ndarray:
    """
    Draw bounding boxes and track labels on a frame.

    For persons:
      - Shows Worker #ID
      - Shows PPE compliance if ppe_states provided
      - Draws a small foot-point indicator (the zone-check point)

    Returns a new annotated frame (does not modify input).
    """
    out = frame.copy()

    for obj in tracked:
        x1, y1, x2, y2 = [int(v) for v in obj.bbox]
        cls = obj.class_name
        color = COLORS.get(cls, COLORS["default"])

        # Skip objects with negative track IDs (unmatched tracker entries)
        if obj.track_id < 0:
            cv2.rectangle(out, (x1, y1), (x2, y2), (128, 128, 128), 1)
            continue

        # Draw bounding box
        cv2.rectangle(out, (x1, y1), (x2, y2), color, 2)

        # Build label
        label = obj.label()
        conf_str = f" {obj.confidence:.2f}"

        if cls == "person" and ppe_states:
            state = ppe_states.get(obj.track_id)
            if state:
                h_icon = "H✓" if state.helmet_detected else "H✗"
                v_icon = "V✓" if state.vest_detected else "V✗"
                label = f"{label} [{h_icon} {v_icon}]"
                # Red box if PPE non-compliant
                if not state.fully_compliant:
                    color = (0, 0, 255)
                    cv2.rectangle(out, (x1, y1), (x2, y2), color, 2)

        # Draw foot-point indicator (zone membership check point)
        if cls == "person":
            foot_x, foot_y = int(obj.foot_x), int(obj.foot_y)
            cv2.circle(out, (foot_x, foot_y), 4, (0, 255, 255), -1)

        # Label background
        text = label + conf_str
        (tw, th), _ = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, 0.45, 1)
        cv2.rectangle(out, (x1, y1 - th - 6), (x1 + tw + 4, y1), color, -1)
        cv2.putText(
            out, text, (x1 + 2, y1 - 3),
            cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 0, 0), 1, cv2.LINE_AA
        )

    return out


def draw_zones(
    frame: np.ndarray,
    zones: list[dict],
) -> np.ndarray:
    """
    Draw semi-transparent zone polygons on the frame.

    zones: list of dicts with keys:
      name, polygon [[x,y],...], color (hex or BGR tuple), severity
    """
    out = frame.copy()
    overlay = frame.copy()

    for zone in zones:
        polygon = zone.get("polygon", [])
        if len(polygon) < 3:
            continue

        pts = np.array(polygon, dtype=np.int32)
        color = _parse_color(zone.get("color", "#FF4444"))

        cv2.fillPoly(overlay, [pts], color)

    # Blend overlay with original
    cv2.addWeighted(overlay, ZONE_ALPHA, out, 1 - ZONE_ALPHA, 0, out)

    # Draw zone outlines and labels on top (fully opaque)
    for zone in zones:
        polygon = zone.get("polygon", [])
        if len(polygon) < 3:
            continue

        pts = np.array(polygon, dtype=np.int32)
        color = _parse_color(zone.get("color", "#FF4444"))
        cv2.polylines(out, [pts], isClosed=True, color=color, thickness=2)

        # Zone label at centroid
        centroid_x = int(pts[:, 0].mean())
        centroid_y = int(pts[:, 1].mean())
        cv2.putText(
            out, zone.get("name", "Zone"),
            (centroid_x, centroid_y),
            cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2, cv2.LINE_AA
        )

    return out


def draw_event_overlay(
    frame: np.ndarray,
    events: list[dict],
) -> np.ndarray:
    """
    Draw active event banners at the bottom of the frame.

    events: list of dicts with keys: description, severity
    """
    out = frame.copy()
    h, w = out.shape[:2]

    for i, evt in enumerate(events[:3]):  # max 3 overlays
        severity = evt.get("severity", "HIGH")
        color = SEVERITY_COLORS.get(severity, (0, 0, 255))
        desc = evt.get("description", "Safety Event")

        y = h - 30 - i * 30
        cv2.rectangle(out, (0, y - 20), (w, y + 6), color, -1)
        cv2.putText(
            out, f"⚠ {severity}: {desc}",
            (10, y),
            cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 255, 255), 1, cv2.LINE_AA
        )

    return out


def draw_metrics(
    frame: np.ndarray,
    fps: float,
    inference_ms: float,
    tracking_ms: float,
    frame_idx: int,
) -> np.ndarray:
    """Draw processing metrics in the top-right corner."""
    out = frame.copy()
    h, w = out.shape[:2]

    lines = [
        f"FPS: {fps:.1f}",
        f"YOLO: {inference_ms:.0f}ms",
        f"Track: {tracking_ms:.0f}ms",
        f"Frame: {frame_idx}",
    ]

    for i, line in enumerate(lines):
        y = 20 + i * 20
        (tw, _), _ = cv2.getTextSize(line, cv2.FONT_HERSHEY_SIMPLEX, 0.45, 1)
        cv2.rectangle(out, (w - tw - 10, y - 14), (w - 2, y + 4), (0, 0, 0), -1)
        cv2.putText(
            out, line, (w - tw - 8, y),
            cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 255, 255), 1, cv2.LINE_AA
        )

    return out


def save_evidence_frame(
    frame: np.ndarray,
    path: str,
    event_description: str,
    severity: str = "HIGH",
) -> None:
    """
    Save an annotated evidence frame to disk.

    Adds a prominent banner with the event description and severity.
    """
    out = frame.copy()
    h, w = out.shape[:2]
    color = SEVERITY_COLORS.get(severity, (0, 0, 255))

    # Top banner
    cv2.rectangle(out, (0, 0), (w, 40), (0, 0, 0), -1)
    cv2.putText(
        out, f"SAFETY EVENT [{severity}]: {event_description}",
        (10, 26),
        cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2, cv2.LINE_AA
    )

    cv2.imwrite(path, out)
    logger.info("Evidence frame saved: %s", path)


def draw_proximity_lines(
    frame: np.ndarray,
    proximity_events: list[dict],
) -> np.ndarray:
    """
    Draw warning line and distance label between person and forklift.
    proximity_events contains dicts with keys:
        person_pt: [x, y], forklift_pt: [x, y], distance: float
    """
    out = frame.copy()
    for ev in proximity_events:
        ppt = ev.get("person_pt") or ev.get("person_foot")
        fpt = ev.get("forklift_pt") or ev.get("forklift_center")
        dist = ev.get("distance_pixels") or ev.get("distance", 0.0)
        if ppt and fpt:
            p1 = (int(ppt[0]), int(ppt[1]))
            p2 = (int(fpt[0]), int(fpt[1]))
            # Red dotted/warning line
            cv2.line(out, p1, p2, (0, 0, 255), 2, cv2.LINE_AA)
            mid = ((p1[0] + p2[0]) // 2, (p1[1] + p2[1]) // 2)
            cv2.putText(
                out, f"DANGER: {dist:.0f}px", mid,
                cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 255), 2, cv2.LINE_AA
            )
    return out


# ─────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────

def _parse_color(color: str | tuple) -> tuple:
    """Convert hex color string to BGR tuple."""
    if isinstance(color, (tuple, list)):
        return tuple(color)

    color = color.lstrip("#")
    if len(color) == 6:
        r = int(color[0:2], 16)
        g = int(color[2:4], 16)
        b = int(color[4:6], 16)
        return (b, g, r)  # BGR
    return (128, 128, 128)
