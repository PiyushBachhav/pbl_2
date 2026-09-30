"""
Object tracker wrapping Ultralytics BoT-SORT / ByteTrack.

Purpose:
  Convert per-frame detections into persistent tracked objects.
  Frame-by-frame "person" becomes "Worker #27" across the whole video.

Ultralytics includes BoT-SORT and ByteTrack internally.
We use BoT-SORT as the default — it handles re-identification better
than pure ByteTrack when objects are temporarily occluded.

Architecture note:
  The tracker only assigns IDs. PPE state, zone membership, and safety
  rule evaluation happen downstream.
"""

from __future__ import annotations

import logging
from typing import Optional

import numpy as np

from app.vision.detections import Detection, TrackedObject

logger = logging.getLogger(__name__)


class ObjectTracker:
    """
    Wraps Ultralytics YOLO's built-in BoT-SORT tracker.

    We use the YOLO model's track() method, which integrates BoT-SORT
    with YOLO's detector output. This gives us stable IDs with minimal
    extra code.

    Alternative: ByteTrack is available via tracker='bytetrack.yaml'.
    Switch by changing the tracker_type parameter.
    """

    def __init__(
        self,
        model,  # Ultralytics YOLO model instance
        tracker_type: str = "botsort",
        confidence: float = 0.35,
        iou: float = 0.5,
        imgsz: int = 640,
        device: str = "cpu",
    ):
        self._model = model
        self._tracker_type = tracker_type
        self._confidence = confidence
        self._iou = iou
        self._imgsz = imgsz
        self._device = device
        self._tracker_config = f"{tracker_type}.yaml"

        logger.info(
            "ObjectTracker initialized | tracker=%s conf=%.2f",
            tracker_type,
            confidence,
        )

    def track(
        self,
        frame: np.ndarray,
        frame_idx: int = 0,
        timestamp: float = 0.0,
        class_map: Optional[dict[int, str]] = None,
    ) -> list[TrackedObject]:
        """
        Run detection + tracking on a single frame.

        Returns TrackedObject list with stable track_ids.
        Objects without an assigned track_id (new in this frame, not yet
        associated) are returned with a synthetic negative ID and filtered
        downstream.
        """
        from app.vision.detector import CLASS_MAP

        if class_map is None:
            class_map = CLASS_MAP

        results = self._model.track(
            source=frame,
            conf=self._confidence,
            iou=self._iou,
            imgsz=self._imgsz,
            device=self._device,
            tracker=self._tracker_config,
            persist=True,   # Required: maintain tracker state between calls
            verbose=False,
            stream=False,
        )

        tracked: list[TrackedObject] = []

        for result in results:
            if result.boxes is None:
                continue

            boxes = result.boxes
            ids = boxes.id  # None if tracker hasn't assigned IDs yet

            for i, box in enumerate(boxes):
                class_id = int(box.cls.item())

                if class_id not in class_map:
                    continue  # Skip classes not in our V1 map

                bbox = box.xyxy[0].tolist()
                confidence = float(box.conf.item())

                # Track ID is None for the first frame or unmatched detections
                if ids is not None and ids[i] is not None:
                    track_id = int(ids[i].item())
                else:
                    # Assign a temporary negative ID to indicate "untracked"
                    track_id = -(i + 1)

                det = Detection(
                    bbox=bbox,
                    class_id=class_id,
                    class_name=class_map[class_id],
                    confidence=confidence,
                    frame_idx=frame_idx,
                    timestamp=timestamp,
                )
                tracked_obj = TrackedObject(track_id=track_id, detection=det)
                tracked.append(tracked_obj)

        if tracked:
            logger.debug(
                "Frame %d | tracked %d objects | IDs: %s",
                frame_idx,
                len(tracked),
                [t.track_id for t in tracked],
            )

        return tracked
