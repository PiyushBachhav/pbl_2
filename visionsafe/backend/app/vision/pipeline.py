"""
Main vision pipeline — orchestrates the full frame processing chain.

Pipeline (spec section 6):
  Video
    ↓  FileVideoSource.frames()
  Frame extraction
    ↓  YOLODetector + ObjectTracker
  YOLO detection + tracking
    ↓  association.build_ppe_states()
  PPE association
    ↓  FrameResult
  Output (database / WebSocket / annotated video)

This module contains:
  InferencePipeline — runs the pipeline on a VideoSource.
  AnnotatedVideoWriter — saves annotated output video.

The safety engine is deliberately NOT imported here.
The pipeline produces FrameResults; the safety engine evaluates them.
This separation means the pipeline can be tested independently.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

import cv2
import numpy as np

from app.vision.detections import FrameResult, TrackedObject
from app.vision.video_source import VideoSource, FileVideoSource
from app.vision.association import build_ppe_states, AssociationConfig
from app.vision.annotator import (
    draw_tracked_objects,
    draw_zones,
    draw_metrics,
)

logger = logging.getLogger(__name__)


@dataclass
class PipelineConfig:
    """Runtime configuration for the inference pipeline."""

    model_path: str = "yolov8n.pt"
    device: str = "cpu"
    confidence: float = 0.35
    iou: float = 0.5
    imgsz: int = 640
    frame_skip: int = 1
    tracker_type: str = "botsort"
    warmup: bool = True
    association_config: AssociationConfig = field(default_factory=AssociationConfig)


class InferencePipeline:
    """
    Runs YOLO + tracker + PPE association on a VideoSource.

    Usage:
        pipeline = InferencePipeline(config)
        pipeline.setup()
        for frame_result in pipeline.process(source):
            # handle FrameResult
        pipeline.teardown()

    Or use as a context manager:
        with InferencePipeline(config) as pipeline:
            for frame_result in pipeline.process(source):
                ...
    """

    def __init__(self, config: Optional[PipelineConfig] = None):
        self._config = config or PipelineConfig()
        self._model = None      # Ultralytics YOLO model
        self._tracker = None    # ObjectTracker

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def setup(self) -> None:
        """Load model and tracker. Call once before processing."""
        from ultralytics import YOLO
        from app.vision.tracker import ObjectTracker

        cfg = self._config

        logger.info(
            "Pipeline setup | model=%s device=%s conf=%.2f imgsz=%d",
            cfg.model_path,
            cfg.device,
            cfg.confidence,
            cfg.imgsz,
        )

        self._model = YOLO(cfg.model_path)

        self._tracker = ObjectTracker(
            model=self._model,
            tracker_type=cfg.tracker_type,
            confidence=cfg.confidence,
            iou=cfg.iou,
            imgsz=cfg.imgsz,
            device=cfg.device,
        )

        if cfg.warmup:
            self._warmup()

    def teardown(self) -> None:
        """Release GPU/model resources."""
        self._model = None
        self._tracker = None
        logger.info("Pipeline resources released.")

    def __enter__(self):
        self.setup()
        return self

    def __exit__(self, *args):
        self.teardown()

    # ------------------------------------------------------------------
    # Processing
    # ------------------------------------------------------------------

    def process(
        self,
        source: VideoSource,
        on_frame: Optional[Callable[[FrameResult, np.ndarray], None]] = None,
        progress_callback: Optional[Callable[[int, int], None]] = None,
    ):
        """
        Process all frames from a VideoSource.

        Yields FrameResult for each processed frame.

        Args:
            source: An opened VideoSource.
            on_frame: Optional callback(frame_result, raw_frame).
                      Called after each frame for side effects (e.g., writing video).
            progress_callback: Optional callback(frames_done, total_frames).
        """
        if self._tracker is None:
            raise RuntimeError("Call setup() before process().")

        cfg = self._config
        total = source.metadata.total_frames if source.metadata else 0

        fps_window: list[float] = []
        last_fps = 0.0
        frames_done = 0

        for frame_idx, timestamp, frame in source.frames():
            t_frame_start = time.perf_counter()

            # --- Tracking (includes YOLO detection internally) ---
            t_track_start = time.perf_counter()
            tracked_objects = self._tracker.track(
                frame,
                frame_idx=frame_idx,
                timestamp=timestamp,
            )
            tracking_ms = (time.perf_counter() - t_track_start) * 1000

            # --- PPE association ---
            persons = [t for t in tracked_objects if t.class_name == "person"]
            helmets = [t for t in tracked_objects if t.class_name == "helmet"]
            vests = [t for t in tracked_objects if t.class_name == "vest"]

            ppe_states = build_ppe_states(
                persons=persons,
                helmets=helmets,
                vests=vests,
                config=cfg.association_config,
            )

            # Attach PPE state to each person TrackedObject
            for person in persons:
                state = ppe_states.get(person.track_id)
                if state:
                    person.ppe_state = state

            # --- Build FrameResult ---
            total_ms = (time.perf_counter() - t_frame_start) * 1000
            frame_result = FrameResult(
                frame_idx=frame_idx,
                timestamp=timestamp,
                tracked_objects=tracked_objects,
                processing_time_ms=total_ms,
                inference_time_ms=total_ms - tracking_ms,  # approx
                tracking_ms=tracking_ms,
            )

            # FPS tracking (rolling window of 30 frames)
            fps_window.append(total_ms)
            if len(fps_window) > 30:
                fps_window.pop(0)
            avg_ms = sum(fps_window) / len(fps_window)
            last_fps = 1000.0 / avg_ms if avg_ms > 0 else 0.0

            if on_frame:
                on_frame(frame_result, frame)

            frames_done += 1
            if progress_callback and total > 0:
                progress_callback(frames_done, total)

            if frame_idx % 30 == 0:
                logger.info(
                    "Frame %d | %.1f FPS | %d objects | %.1f ms/frame",
                    frame_idx,
                    last_fps,
                    len(tracked_objects),
                    total_ms,
                )

            yield frame_result

    # ------------------------------------------------------------------
    # Private
    # ------------------------------------------------------------------

    def _warmup(self) -> None:
        """Run one dummy frame to initialize CUDA kernels."""
        logger.info("Warming up pipeline...")
        dummy = np.zeros((self._config.imgsz, self._config.imgsz, 3), dtype=np.uint8)
        self._tracker.track(dummy, frame_idx=-1, timestamp=0.0)
        logger.info("Pipeline warmup complete.")


class AnnotatedVideoWriter:
    """
    Writes an annotated output video from pipeline FrameResults.

    Used for Phase 2: video → YOLO → annotated output video.
    """

    def __init__(
        self,
        output_path: str | Path,
        fps: float,
        width: int,
        height: int,
    ):
        self._path = Path(output_path)
        self._fps = fps
        self._width = width
        self._height = height
        self._writer: Optional[cv2.VideoWriter] = None

    def open(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        fourcc = cv2.VideoWriter_fourcc(*"mp4v")
        self._writer = cv2.VideoWriter(
            str(self._path), fourcc, self._fps, (self._width, self._height)
        )
        if not self._writer.isOpened():
            raise RuntimeError(f"Could not open video writer: {self._path}")
        logger.info("Writing annotated video to: %s", self._path)

    def write(
        self,
        frame: np.ndarray,
        frame_result: FrameResult,
        fps: float = 0.0,
        zones: Optional[list[dict]] = None,
    ) -> None:
        """
        Annotate frame with tracked objects and write to output.

        Args:
            frame:        Raw BGR frame from the video source.
            frame_result: Pipeline output for this frame.
            fps:          Current processing FPS (for overlay).
            zones:        Optional list of zone dicts for polygon drawing.
        """
        out = frame.copy()

        # Draw zones first (background)
        if zones:
            out = draw_zones(out, zones)

        # Draw tracked objects with PPE status
        ppe_map = {
            p.track_id: p.ppe_state
            for p in frame_result.persons
            if p.ppe_state
        }
        out = draw_tracked_objects(out, frame_result.tracked_objects, ppe_map)

        # Draw metrics overlay
        out = draw_metrics(
            out,
            fps=fps,
            inference_ms=frame_result.inference_time_ms,
            tracking_ms=frame_result.tracking_ms,
            frame_idx=frame_result.frame_idx,
        )

        self._writer.write(out)

    def close(self) -> None:
        if self._writer is not None:
            self._writer.release()
            self._writer = None
        logger.info("Video writer closed: %s", self._path)

    def __enter__(self):
        self.open()
        return self

    def __exit__(self, *args):
        self.close()
