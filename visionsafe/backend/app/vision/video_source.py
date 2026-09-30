"""
Video source abstraction.

Architecture note (spec section 21):
  V1 supports only uploaded MP4 files (FileVideoSource).
  The VideoSource ABC enables adding RTSP/WebRTC/USB sources later
  without changing any downstream code.

  V2 sources to implement:
    RTSPVideoSource   — RTSP stream via cv2.VideoCapture("rtsp://...")
    CameraVideoSource — Local USB/webcam via cv2.VideoCapture(device_id)
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import Generator, Optional

import cv2
import numpy as np

logger = logging.getLogger(__name__)


@dataclass
class VideoMetadata:
    """Basic metadata extracted from a video source."""

    width: int
    height: int
    fps: float
    total_frames: int
    duration_seconds: float
    source_path: str


class VideoSource(ABC):
    """
    Abstract video source.

    All implementations must yield (frame_idx, timestamp_sec, frame_bgr)
    tuples from the frames() generator.
    """

    @abstractmethod
    def open(self) -> None:
        """Open/connect to the video source."""
        ...

    @abstractmethod
    def close(self) -> None:
        """Release resources."""
        ...

    @abstractmethod
    def frames(self) -> Generator[tuple[int, float, np.ndarray], None, None]:
        """
        Yield (frame_idx, timestamp_seconds, bgr_frame) tuples.

        frame_idx: zero-based frame counter.
        timestamp_seconds: position in seconds for file sources,
                           wall time for live sources.
        bgr_frame: BGR numpy array (OpenCV convention).
        """
        ...

    @property
    @abstractmethod
    def metadata(self) -> Optional[VideoMetadata]:
        """Return metadata after open() has been called."""
        ...

    def __enter__(self):
        self.open()
        return self

    def __exit__(self, *args):
        self.close()


class FileVideoSource(VideoSource):
    """
    Video source reading frames from a local file (MP4, AVI, etc.).

    Uses OpenCV VideoCapture. Supports configurable frame_skip so that
    every Nth frame is processed (useful for performance on long videos).

    Processing frequency is configurable — not hard-coded.
    """

    def __init__(self, file_path: str | Path, frame_skip: int = 1):
        """
        Args:
            file_path:  Path to the video file.
            frame_skip: Process every Nth frame. 1 = every frame.
        """
        self._path = Path(file_path)
        self._frame_skip = max(1, frame_skip)
        self._cap: Optional[cv2.VideoCapture] = None
        self._metadata: Optional[VideoMetadata] = None

    def open(self) -> None:
        if not self._path.exists():
            raise FileNotFoundError(f"Video file not found: {self._path}")

        self._cap = cv2.VideoCapture(str(self._path))
        if not self._cap.isOpened():
            raise RuntimeError(f"Could not open video file: {self._path}")

        fps = self._cap.get(cv2.CAP_PROP_FPS) or 25.0
        total = int(self._cap.get(cv2.CAP_PROP_FRAME_COUNT))
        width = int(self._cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(self._cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

        self._metadata = VideoMetadata(
            width=width,
            height=height,
            fps=fps,
            total_frames=total,
            duration_seconds=total / fps if fps > 0 else 0.0,
            source_path=str(self._path),
        )

        logger.info(
            "Opened video | file=%s fps=%.1f frames=%d res=%dx%d frame_skip=%d",
            self._path.name,
            fps,
            total,
            width,
            height,
            self._frame_skip,
        )

    def close(self) -> None:
        if self._cap is not None:
            self._cap.release()
            self._cap = None
        logger.info("Video source closed.")

    @property
    def metadata(self) -> Optional[VideoMetadata]:
        return self._metadata

    def frames(self) -> Generator[tuple[int, float, np.ndarray], None, None]:
        """
        Yield frames, skipping every (frame_skip - 1) frames.

        Timestamp is computed from frame position and FPS.
        """
        if self._cap is None:
            raise RuntimeError("Call open() before frames().")

        fps = self._metadata.fps if self._metadata else 25.0
        frame_idx = 0

        while True:
            ret, frame = self._cap.read()
            if not ret:
                break

            if frame_idx % self._frame_skip == 0:
                timestamp = frame_idx / fps
                yield frame_idx, timestamp, frame

            frame_idx += 1
