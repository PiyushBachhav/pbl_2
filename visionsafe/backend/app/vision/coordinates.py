"""
Coordinate transformation abstraction.

Architecture note (spec section 15):
  For V1, all distances are in image-pixel coordinates.
  This is an approximation; pixels are NOT meters.
  The UI must clearly state "Image-space distance" wherever pixel distances
  are displayed.

Future V2 plan:
  Add HomographyCoordinateTransformer that converts image coordinates to
  ground-plane world coordinates using a camera calibration homography matrix.
  The safety engine reads world coordinates and compares with real distances.

  Pipeline:
    Image (px) → Homography → Ground plane (m)

The transformer abstraction keeps the safety engine decoupled from
the coordinate system. Only one line changes when switching to
calibrated coordinates.
"""

from __future__ import annotations

import math
from abc import ABC, abstractmethod
from typing import Tuple

import numpy as np


Point2D = Tuple[float, float]  # (x, y) in any coordinate space


class CoordinateTransformer(ABC):
    """
    Abstract coordinate transformer.

    All distances computed by the safety engine go through this interface.
    """

    @abstractmethod
    def image_to_world(self, point: Point2D) -> Point2D:
        """
        Transform a point from image pixel coordinates to world coordinates.

        V1: identity (returns pixel coordinates unchanged).
        V2: applies homography to convert pixels to ground-plane meters.
        """
        ...

    @abstractmethod
    def distance(self, a: Point2D, b: Point2D) -> float:
        """
        Compute distance between two world-space points.

        V1: Euclidean pixel distance (approximation).
        V2: Euclidean metric distance in meters.
        """
        ...

    @property
    @abstractmethod
    def unit(self) -> str:
        """Human-readable unit string for display, e.g. 'px' or 'm'."""
        ...

    @property
    @abstractmethod
    def is_calibrated(self) -> bool:
        """True if this transformer produces real-world metric distances."""
        ...


class ImageCoordinateTransformer(CoordinateTransformer):
    """
    V1 no-op transformer.

    Returns image-space pixel coordinates unchanged.
    All distances are in pixels — NOT meters.

    The UI must clearly display "Image-space distance (px)" wherever
    values from this transformer are shown, to avoid misrepresenting
    pixel distances as real workplace safety distances.
    """

    def image_to_world(self, point: Point2D) -> Point2D:
        """Identity transform — pixels in, pixels out."""
        return point

    def distance(self, a: Point2D, b: Point2D) -> float:
        """Euclidean pixel distance between two image points."""
        return math.sqrt((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2)

    @property
    def unit(self) -> str:
        return "px"

    @property
    def is_calibrated(self) -> bool:
        return False


class HomographyCoordinateTransformer(CoordinateTransformer):
    """
    V2 homography transformer (stub — not implemented in MVP).

    To implement:
      1. Calibrate camera using at least 4 ground-plane reference points.
      2. Compute homography matrix H using cv2.findHomography().
      3. Pass H to this class.
      4. Replace ImageCoordinateTransformer with this in the safety engine.

    All distances then become real-world meters.
    """

    def __init__(self, homography_matrix: np.ndarray):
        if homography_matrix.shape != (3, 3):
            raise ValueError("Homography matrix must be 3×3.")
        self._H = homography_matrix

    def image_to_world(self, point: Point2D) -> Point2D:
        """Apply homography to convert image point to ground-plane coordinates."""
        import cv2
        pt = np.array([[[point[0], point[1]]]], dtype=np.float32)
        world = cv2.perspectiveTransform(pt, self._H)
        return (float(world[0][0][0]), float(world[0][0][1]))

    def distance(self, a: Point2D, b: Point2D) -> float:
        """Euclidean metric distance between two world points (in meters if H calibrated)."""
        wa = self.image_to_world(a)
        wb = self.image_to_world(b)
        return math.sqrt((wa[0] - wb[0]) ** 2 + (wa[1] - wb[1]) ** 2)

    @property
    def unit(self) -> str:
        return "m"

    @property
    def is_calibrated(self) -> bool:
        return True
