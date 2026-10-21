"""
Detection data structures shared across the vision and safety layers.

These dataclasses are the contract between:
  YOLO detector → tracker → safety engine

All coordinates are in image-pixel space unless explicitly stated otherwise.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Detection:
    """
    A single object detection from one frame.

    bbox: [x1, y1, x2, y2] in pixel coordinates (top-left, bottom-right).
    class_id: integer label index (0=person, 1=helmet, 2=vest, 3=forklift).
    class_name: human-readable label.
    confidence: detector confidence score in [0, 1].
    frame_idx: zero-based frame number within the video.
    timestamp: wall-clock or video time in seconds.
    """

    bbox: list[float]          # [x1, y1, x2, y2]
    class_id: int
    class_name: str
    confidence: float
    frame_idx: int = 0
    timestamp: float = 0.0

    @property
    def x1(self) -> float:
        return self.bbox[0]

    @property
    def y1(self) -> float:
        return self.bbox[1]

    @property
    def x2(self) -> float:
        return self.bbox[2]

    @property
    def y2(self) -> float:
        return self.bbox[3]

    @property
    def width(self) -> float:
        return self.x2 - self.x1

    @property
    def height(self) -> float:
        return self.y2 - self.y1

    @property
    def center_x(self) -> float:
        return (self.x1 + self.x2) / 2.0

    @property
    def center_y(self) -> float:
        return (self.y1 + self.y2) / 2.0

    @property
    def area(self) -> float:
        return self.width * self.height


@dataclass
class TrackedObject:
    """
    A detection that has been assigned a stable track ID by the tracker.

    Design note — foot position:
        For people, zone membership is determined using the foot point
        (bottom-center of bounding box) rather than the bbox center.
        This is because safety zones are floor-based regions, and the
        bottom-center approximates where feet contact the ground plane.
        Reference: Section 8 of VisionSafe architecture specification.

    track_id: persistent integer assigned by the tracker across frames.
    foot_x / foot_y: bottom-center of bbox — used for zone checks on people.
    ppe_state: populated by the PPE association engine (not the tracker).
    """

    track_id: int
    detection: Detection
    foot_x: float = field(init=False)
    foot_y: float = field(init=False)
    ppe_state: Optional["PPEState"] = field(default=None, repr=False)

    def __post_init__(self):
        # Foot position: bottom-center of bounding box.
        # See architecture section 8 for the rationale.
        self.foot_x = (self.detection.x1 + self.detection.x2) / 2.0
        self.foot_y = self.detection.y2

    @property
    def class_name(self) -> str:
        return self.detection.class_name

    @property
    def class_id(self) -> int:
        return self.detection.class_id

    @property
    def confidence(self) -> float:
        return self.detection.confidence

    @property
    def bbox(self) -> list[float]:
        return self.detection.bbox

    @property
    def center_x(self) -> float:
        return self.detection.center_x

    @property
    def center_y(self) -> float:
        return self.detection.center_y

    @property
    def timestamp(self) -> float:
        return self.detection.timestamp

    @property
    def frame_idx(self) -> int:
        return self.detection.frame_idx

    def label(self) -> str:
        """Human-readable label, e.g. 'Worker #27' or 'Forklift #3'."""
        if self.class_name == "person":
            return f"Worker #{self.track_id}"
        elif self.class_name == "forklift":
            return f"Forklift #{self.track_id}"
        return f"{self.class_name.title()} #{self.track_id}"


@dataclass
class PPEState:
    """
    The PPE compliance state for a single tracked person.

    Populated by vision/association.py after detector output.
    helmet_confidence / vest_confidence are the detection confidences
    of the associated PPE objects (None if not detected).
    """

    person_track_id: int
    helmet_detected: bool = False
    helmet_confidence: Optional[float] = None
    vest_detected: bool = False
    vest_confidence: Optional[float] = None

    @property
    def fully_compliant(self) -> bool:
        return self.helmet_detected and self.vest_detected

    def missing_ppe(self) -> list[str]:
        missing = []
        if not self.helmet_detected:
            missing.append("helmet")
        if not self.vest_detected:
            missing.append("vest")
        return missing


@dataclass
class FrameResult:
    """
    Complete output for a single processed frame.

    Carries tracked objects after the full pipeline:
      YOLO → tracker → PPE association → (safety engine reads this)
    """

    frame_idx: int
    timestamp: float
    tracked_objects: list[TrackedObject]
    processing_time_ms: float = 0.0
    inference_time_ms: float = 0.0
    tracking_time_ms: float = 0.0

    @property
    def tracking_ms(self) -> float:
        return self.tracking_time_ms

    @property
    def persons(self) -> list[TrackedObject]:
        return [t for t in self.tracked_objects if t.class_name == "person"]

    @property
    def forklifts(self) -> list[TrackedObject]:
        return [t for t in self.tracked_objects if t.class_name == "forklift"]

    @property
    def helmets(self) -> list[TrackedObject]:
        return [t for t in self.tracked_objects if t.class_name == "helmet"]

    @property
    def vests(self) -> list[TrackedObject]:
        return [t for t in self.tracked_objects if t.class_name == "vest"]
