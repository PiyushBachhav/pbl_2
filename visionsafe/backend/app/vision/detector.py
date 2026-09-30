"""
Object detector abstraction and YOLO implementation.

Architecture principle:
  ObjectDetector is an interface. The safety engine depends ONLY on this
  interface, never on YOLO directly. This allows swapping YOLO for another
  detector without touching any downstream code.

Class label map (V1):
  0 = person
  1 = helmet
  2 = vest
  3 = forklift

The model is loaded once and reused across frames.
"""

from __future__ import annotations

import logging
import time
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Optional

import numpy as np

from app.vision.detections import Detection

logger = logging.getLogger(__name__)

# V1 class map — must match the training dataset configuration.
# Adding new classes requires updating this map AND retraining.
CLASS_MAP: dict[int, str] = {
    0: "person",
    1: "helmet",
    2: "vest",
    3: "forklift",
}


class ObjectDetector(ABC):
    """
    Abstract interface for object detectors.

    All detectors must implement detect(frame) → list[Detection].
    The safety engine depends on this interface, not on YOLO.
    """

    @abstractmethod
    def detect(self, frame: np.ndarray, frame_idx: int = 0, timestamp: float = 0.0) -> list[Detection]:
        """
        Run inference on a single BGR frame.

        Args:
            frame: BGR image as a numpy array (OpenCV convention).
            frame_idx: zero-based frame number in the video.
            timestamp: video time in seconds.

        Returns:
            List of Detection objects for this frame.
        """
        ...

    @property
    @abstractmethod
    def class_map(self) -> dict[int, str]:
        """Return the {class_id: class_name} mapping."""
        ...

    @abstractmethod
    def warmup(self) -> None:
        """Run a dummy inference to warm up GPU/model."""
        ...


class YOLODetector(ObjectDetector):
    """
    YOLO object detector implemented via Ultralytics.

    Model selection:
      - yolov8n.pt  → fastest, lowest accuracy, ~4 ms/frame on RTX 3050
      - yolov8s.pt  → balanced (recommended for production on 4GB GPU)
      - yolov8m.pt  → higher accuracy, higher VRAM usage

    For the RTX 3050 4GB, yolov8n is the safe default.
    The model path is fully configurable via environment or constructor.

    If the requested device is CUDA and no GPU is available, falls back to CPU
    with a warning rather than crashing.
    """

    def __init__(
        self,
        model_path: str = "yolov8n.pt",
        device: str = "cpu",
        confidence: float = 0.35,
        iou: float = 0.5,
        imgsz: int = 640,
        class_filter: Optional[list[int]] = None,
    ):
        """
        Args:
            model_path: Path to a .pt model file or a model name like 'yolov8n.pt'
                        (Ultralytics will auto-download named models on first run).
            device:     'cpu', 'cuda', or '0' for CUDA device 0.
            confidence: Minimum detection confidence threshold.
            iou:        NMS IoU threshold.
            imgsz:      Input image size for inference (width=height).
            class_filter: If set, only return detections for these class IDs.
        """
        self._model_path = model_path
        self._device = self._resolve_device(device)
        self._confidence = confidence
        self._iou = iou
        self._imgsz = imgsz
        self._class_filter = class_filter
        self._model = None

        self._load_model()

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _resolve_device(self, requested: str) -> str:
        """Validate requested device; fall back to CPU if CUDA unavailable."""
        if requested in ("cuda", "0", "gpu"):
            try:
                import torch
                if torch.cuda.is_available():
                    device_name = torch.cuda.get_device_name(0)
                    vram_mb = torch.cuda.get_device_properties(0).total_memory // (1024 ** 2)
                    logger.info("CUDA available: %s (%d MB VRAM)", device_name, vram_mb)
                    return "0"  # Ultralytics prefers "0" for CUDA device 0
                else:
                    logger.warning(
                        "CUDA requested but not available — falling back to CPU. "
                        "Install PyTorch with CUDA support for GPU acceleration."
                    )
                    return "cpu"
            except ImportError:
                logger.warning("PyTorch not importable — using CPU.")
                return "cpu"
        return requested

    def _load_model(self) -> None:
        """Load YOLO model from path. Auto-downloads if a model name is given."""
        from ultralytics import YOLO

        model_path = Path(self._model_path)
        if not model_path.exists() and "/" not in self._model_path and "\\" not in self._model_path:
            # Named model like "yolov8n.pt" — Ultralytics downloads to its cache
            logger.info("Model file not found locally; Ultralytics will download '%s'", self._model_path)
        else:
            logger.info("Loading model from '%s'", model_path.resolve())

        self._model = YOLO(self._model_path)
        self._model.to(self._device)
        logger.info(
            "YOLODetector ready | model=%s device=%s conf=%.2f iou=%.2f imgsz=%d",
            self._model_path,
            self._device,
            self._confidence,
            self._iou,
            self._imgsz,
        )

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    @property
    def class_map(self) -> dict[int, str]:
        return CLASS_MAP

    def warmup(self) -> None:
        """Run a dummy inference to initialize GPU kernels."""
        logger.info("Warming up model on device '%s'...", self._device)
        dummy = np.zeros((self._imgsz, self._imgsz, 3), dtype=np.uint8)
        self.detect(dummy)
        logger.info("Model warmup complete.")

    def detect(
        self,
        frame: np.ndarray,
        frame_idx: int = 0,
        timestamp: float = 0.0,
    ) -> list[Detection]:
        """
        Run YOLO inference on a BGR frame and return structured detections.

        Ultralytics returns results in xyxy format (x1, y1, x2, y2).
        We keep only detections whose class_id is in CLASS_MAP.
        """
        if self._model is None:
            raise RuntimeError("Model not loaded. Call _load_model() first.")

        results = self._model.predict(
            source=frame,
            conf=self._confidence,
            iou=self._iou,
            imgsz=self._imgsz,
            device=self._device,
            verbose=False,
            stream=False,
        )

        detections: list[Detection] = []
        for result in results:
            if result.boxes is None:
                continue
            for box in result.boxes:
                class_id = int(box.cls.item())

                # Skip classes not in our V1 map
                if class_id not in CLASS_MAP:
                    continue

                # Apply optional class filter
                if self._class_filter is not None and class_id not in self._class_filter:
                    continue

                bbox = box.xyxy[0].tolist()  # [x1, y1, x2, y2]
                confidence = float(box.conf.item())

                det = Detection(
                    bbox=bbox,
                    class_id=class_id,
                    class_name=CLASS_MAP[class_id],
                    confidence=confidence,
                    frame_idx=frame_idx,
                    timestamp=timestamp,
                )
                detections.append(det)

        return detections
