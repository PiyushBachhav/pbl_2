"""
PPE association engine.

Problem:
  YOLO detects persons, helmets, and vests independently.
  It does NOT tell us which helmet belongs to which person.

Solution:
  Use bounding-box geometry to associate PPE with the nearest person.

Strategy (per architecture spec section 12-13):
  - A helmet is associated with a person if its bbox center falls
    within the upper ~40% of the person's bounding box.
  - A vest is associated with a person if its bbox overlaps the
    middle ~60% of the person's bounding box (torso region).
  - Each PPE item is assigned to at most one person (closest match).

These are geometric heuristics and are configurable via parameters.
They work well in typical upright-person scenarios but may fail with
unusual poses or extreme camera angles. Future work: use pose estimation.

Output:
  Each TrackedObject (person) has a PPEState attached describing
  which PPE items were detected and with what confidence.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional

from app.vision.detections import TrackedObject, PPEState

logger = logging.getLogger(__name__)


@dataclass
class AssociationConfig:
    """
    Configurable thresholds for PPE-to-person geometric association.

    helmet_upper_fraction: Fraction of person bbox height from top
        within which the helmet center must fall to be associated.
        Default 0.4 = upper 40% of person bbox.

    vest_upper_fraction: Top of vest association region (fraction from top).
    vest_lower_fraction: Bottom of vest association region (fraction from top).
        Default 0.3–0.9 = torso region.

    iou_threshold: Minimum intersection/overlap between PPE bbox and
        person bbox to consider association (secondary check).
    """

    helmet_upper_fraction: float = 0.40
    vest_upper_fraction: float = 0.30
    vest_lower_fraction: float = 0.90
    iou_threshold: float = 0.0  # 0 = center-point method only


def _bbox_center(bbox: list[float]) -> tuple[float, float]:
    """Return (cx, cy) center of bbox [x1, y1, x2, y2]."""
    return (bbox[0] + bbox[2]) / 2.0, (bbox[1] + bbox[3]) / 2.0


def _iou(bbox_a: list[float], bbox_b: list[float]) -> float:
    """Intersection over Union of two bboxes [x1, y1, x2, y2]."""
    xa = max(bbox_a[0], bbox_b[0])
    ya = max(bbox_a[1], bbox_b[1])
    xb = min(bbox_a[2], bbox_b[2])
    yb = min(bbox_a[3], bbox_b[3])

    inter_w = max(0.0, xb - xa)
    inter_h = max(0.0, yb - ya)
    inter = inter_w * inter_h

    if inter == 0:
        return 0.0

    area_a = (bbox_a[2] - bbox_a[0]) * (bbox_a[3] - bbox_a[1])
    area_b = (bbox_b[2] - bbox_b[0]) * (bbox_b[3] - bbox_b[1])
    union = area_a + area_b - inter
    return inter / union if union > 0 else 0.0


def associate_helmet_to_person(
    person: TrackedObject,
    helmets: list[TrackedObject],
    config: AssociationConfig,
) -> Optional[TrackedObject]:
    """
    Find the helmet most likely worn by this person.

    Method:
      1. The helmet center (cx, cy) must fall within the person's
         upper `helmet_upper_fraction` of the bounding box.
      2. Among candidates, pick the one closest to the person center.

    Returns None if no helmet is within the association region.
    """
    pb = person.bbox  # [x1, y1, x2, y2]
    person_height = pb[3] - pb[1]
    if person_height <= 0:
        return None

    # Upper region threshold
    upper_y_max = pb[1] + person_height * config.helmet_upper_fraction

    candidates: list[tuple[float, TrackedObject]] = []
    for helmet in helmets:
        hcx, hcy = _bbox_center(helmet.bbox)

        # Must be within horizontal span of person and within upper region
        in_x = pb[0] <= hcx <= pb[2]
        in_y = pb[1] <= hcy <= upper_y_max

        if in_x and in_y:
            # Distance from person center (prefer closest)
            dist = abs(hcx - person.center_x) + abs(hcy - (pb[1] + person_height * 0.15))
            candidates.append((dist, helmet))

    if not candidates:
        return None

    candidates.sort(key=lambda x: x[0])
    return candidates[0][1]


def associate_vest_to_person(
    person: TrackedObject,
    vests: list[TrackedObject],
    config: AssociationConfig,
) -> Optional[TrackedObject]:
    """
    Find the safety vest most likely worn by this person.

    Method:
      1. The vest center (cx, cy) must fall within the person's
         torso region: [vest_upper_fraction, vest_lower_fraction] of bbox height.
      2. Among candidates, pick the one with the most overlap (IoU).

    Returns None if no vest is within the torso region.
    """
    pb = person.bbox
    person_height = pb[3] - pb[1]
    if person_height <= 0:
        return None

    torso_y_min = pb[1] + person_height * config.vest_upper_fraction
    torso_y_max = pb[1] + person_height * config.vest_lower_fraction

    candidates: list[tuple[float, TrackedObject]] = []
    for vest in vests:
        vcx, vcy = _bbox_center(vest.bbox)

        in_x = pb[0] <= vcx <= pb[2]
        in_y = torso_y_min <= vcy <= torso_y_max

        if in_x and in_y:
            overlap = _iou(person.bbox, vest.bbox)
            candidates.append((overlap, vest))

    if not candidates:
        return None

    # Highest IoU wins
    candidates.sort(key=lambda x: x[0], reverse=True)
    return candidates[0][1]


def build_ppe_states(
    persons: list[TrackedObject],
    helmets: list[TrackedObject],
    vests: list[TrackedObject],
    config: Optional[AssociationConfig] = None,
) -> dict[int, PPEState]:
    """
    Build a PPEState for every tracked person in this frame.

    Each PPE item is associated to at most one person.
    Uses a greedy assignment: process persons sorted by confidence desc.

    Args:
        persons: All tracked persons in this frame.
        helmets: All tracked helmets in this frame.
        vests:   All tracked vests in this frame.
        config:  Association geometry parameters.

    Returns:
        {track_id: PPEState} for every person.
    """
    if config is None:
        config = AssociationConfig()

    ppe_states: dict[int, PPEState] = {}
    available_helmets = list(helmets)
    available_vests = list(vests)

    # Process high-confidence persons first to get first pick of PPE
    sorted_persons = sorted(persons, key=lambda p: p.confidence, reverse=True)

    for person in sorted_persons:
        state = PPEState(person_track_id=person.track_id)

        # Associate helmet
        helmet_match = associate_helmet_to_person(person, available_helmets, config)
        if helmet_match is not None:
            state.helmet_detected = True
            state.helmet_confidence = helmet_match.confidence
            available_helmets.remove(helmet_match)

        # Associate vest
        vest_match = associate_vest_to_person(person, available_vests, config)
        if vest_match is not None:
            state.vest_detected = True
            state.vest_confidence = vest_match.confidence
            available_vests.remove(vest_match)

        ppe_states[person.track_id] = state

        logger.debug(
            "PPE | Worker #%d | helmet=%s(%.2f) vest=%s(%.2f)",
            person.track_id,
            state.helmet_detected,
            state.helmet_confidence or 0.0,
            state.vest_detected,
            state.vest_confidence or 0.0,
        )

    return ppe_states
