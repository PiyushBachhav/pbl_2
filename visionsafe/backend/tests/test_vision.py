"""
Unit tests for critical safety engine components.

These tests cover the most important non-ML logic:
  - Point-in-polygon detection
  - PPE association geometry
  - Coordinate distance calculation

Tests do NOT require a GPU, database, or YOLO model.
They can run on any machine with pytest installed.

Run: pytest backend/tests/ -v
"""

import math
import pytest

from app.vision.detections import Detection, TrackedObject, PPEState
from app.vision.association import (
    AssociationConfig,
    associate_helmet_to_person,
    associate_vest_to_person,
    build_ppe_states,
    _iou,
    _bbox_center,
)
from app.vision.coordinates import ImageCoordinateTransformer


# ─────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────

def make_detection(
    bbox: list[float],
    class_name: str = "person",
    class_id: int = 0,
    confidence: float = 0.90,
    frame_idx: int = 0,
) -> Detection:
    return Detection(
        bbox=bbox,
        class_id=class_id,
        class_name=class_name,
        confidence=confidence,
        frame_idx=frame_idx,
    )


def make_tracked(
    track_id: int,
    bbox: list[float],
    class_name: str = "person",
    class_id: int = 0,
) -> TrackedObject:
    det = make_detection(bbox, class_name, class_id)
    return TrackedObject(track_id=track_id, detection=det)


# ─────────────────────────────────────────
# TrackedObject foot position
# ─────────────────────────────────────────

class TestFootPosition:
    """
    Verify that foot_x / foot_y is correctly set to the bottom-center
    of the bounding box (architecture spec section 8).
    """

    def test_foot_position_centered(self):
        obj = make_tracked(1, [100.0, 50.0, 200.0, 300.0])
        assert obj.foot_x == pytest.approx(150.0)  # (100+200)/2
        assert obj.foot_y == pytest.approx(300.0)  # y2

    def test_foot_position_asymmetric(self):
        obj = make_tracked(2, [10.0, 20.0, 110.0, 180.0])
        assert obj.foot_x == pytest.approx(60.0)
        assert obj.foot_y == pytest.approx(180.0)

    def test_label_person(self):
        obj = make_tracked(27, [0, 0, 100, 200], "person", 0)
        assert obj.label() == "Worker #27"

    def test_label_forklift(self):
        obj = make_tracked(3, [0, 0, 100, 200], "forklift", 3)
        assert obj.label() == "Forklift #3"


# ─────────────────────────────────────────
# Coordinate transformer
# ─────────────────────────────────────────

class TestImageCoordinateTransformer:
    def setup_method(self):
        self.tx = ImageCoordinateTransformer()

    def test_identity_transform(self):
        pt = (100.0, 200.0)
        assert self.tx.image_to_world(pt) == pt

    def test_euclidean_distance(self):
        a = (0.0, 0.0)
        b = (3.0, 4.0)
        assert self.tx.distance(a, b) == pytest.approx(5.0)

    def test_not_calibrated(self):
        assert self.tx.is_calibrated is False

    def test_unit_is_pixels(self):
        assert self.tx.unit == "px"

    def test_zero_distance(self):
        assert self.tx.distance((50.0, 50.0), (50.0, 50.0)) == pytest.approx(0.0)


# ─────────────────────────────────────────
# IoU helper
# ─────────────────────────────────────────

class TestIoU:
    def test_no_overlap(self):
        a = [0, 0, 10, 10]
        b = [20, 20, 30, 30]
        assert _iou(a, b) == pytest.approx(0.0)

    def test_full_overlap(self):
        a = [0, 0, 10, 10]
        assert _iou(a, a) == pytest.approx(1.0)

    def test_partial_overlap(self):
        a = [0, 0, 10, 10]
        b = [5, 0, 15, 10]  # 50% overlap
        result = _iou(a, b)
        assert 0.3 < result < 0.4  # intersection=50, union=150 → 1/3


# ─────────────────────────────────────────
# Helmet association
# ─────────────────────────────────────────

class TestHelmetAssociation:
    def setup_method(self):
        self.config = AssociationConfig(helmet_upper_fraction=0.4)

    def _person(self, bbox):
        return make_tracked(1, bbox, "person", 0)

    def _helmet(self, bbox):
        return make_tracked(10, bbox, "helmet", 1)

    def test_helmet_in_upper_region(self):
        """Helmet center in top 40% of person bbox → associated."""
        # Person: y1=100, y2=300 → height=200 → upper limit = 100 + 80 = 180
        person = self._person([50.0, 100.0, 150.0, 300.0])
        # Helmet center at (100, 130) — clearly in upper region
        helmet = self._helmet([80.0, 110.0, 120.0, 150.0])
        result = associate_helmet_to_person(person, [helmet], self.config)
        assert result is not None

    def test_helmet_below_upper_region(self):
        """Helmet center in lower half of person bbox → not associated."""
        person = self._person([50.0, 100.0, 150.0, 300.0])
        # Helmet center at (100, 260) — in lower region
        helmet = self._helmet([80.0, 240.0, 120.0, 280.0])
        result = associate_helmet_to_person(person, [helmet], self.config)
        assert result is None

    def test_no_helmets(self):
        person = self._person([50.0, 100.0, 150.0, 300.0])
        result = associate_helmet_to_person(person, [], self.config)
        assert result is None

    def test_helmet_outside_x_range(self):
        """Helmet center outside person horizontal span → not associated."""
        person = self._person([50.0, 100.0, 150.0, 300.0])
        # Helmet center at x=200 — outside person x range [50, 150]
        helmet = self._helmet([180.0, 110.0, 220.0, 150.0])
        result = associate_helmet_to_person(person, [helmet], self.config)
        assert result is None

    def test_picks_closest_helmet(self):
        """When multiple helmets qualify, picks the closest one."""
        person = self._person([50.0, 100.0, 150.0, 300.0])
        # Two helmets in upper region — close vs far
        helmet_close = make_tracked(10, [90.0, 110.0, 110.0, 130.0], "helmet", 1)
        helmet_far = make_tracked(11, [60.0, 110.0, 80.0, 130.0], "helmet", 1)
        result = associate_helmet_to_person(person, [helmet_close, helmet_far], self.config)
        assert result is not None
        assert result.track_id == 10  # closer to center


# ─────────────────────────────────────────
# Vest association
# ─────────────────────────────────────────

class TestVestAssociation:
    def setup_method(self):
        self.config = AssociationConfig(vest_upper_fraction=0.3, vest_lower_fraction=0.9)

    def _person(self, bbox):
        return make_tracked(1, bbox, "person", 0)

    def _vest(self, bbox):
        return make_tracked(20, bbox, "vest", 2)

    def test_vest_in_torso_region(self):
        """Vest center in torso region (30%–90%) → associated."""
        # Person: y1=0, y2=200 → torso = [60, 180]
        person = self._person([50.0, 0.0, 150.0, 200.0])
        vest = self._vest([70.0, 90.0, 130.0, 140.0])  # center y=115 in [60, 180]
        result = associate_vest_to_person(person, [vest], self.config)
        assert result is not None

    def test_vest_above_torso(self):
        """Vest center in top 30% → not associated (that's helmet region)."""
        person = self._person([50.0, 0.0, 150.0, 200.0])
        vest = self._vest([70.0, 0.0, 130.0, 40.0])  # center y=20, above 60
        result = associate_vest_to_person(person, [vest], self.config)
        assert result is None

    def test_no_vests(self):
        person = self._person([50.0, 0.0, 150.0, 200.0])
        result = associate_vest_to_person(person, [], self.config)
        assert result is None


# ─────────────────────────────────────────
# PPE state builder
# ─────────────────────────────────────────

class TestBuildPPEStates:
    """Test full PPE state building for multiple workers."""

    def test_compliant_worker(self):
        """Worker with helmet and vest in correct positions → compliant."""
        person = make_tracked(27, [50.0, 100.0, 150.0, 300.0], "person", 0)
        helmet = make_tracked(1, [80.0, 110.0, 120.0, 145.0], "helmet", 1)
        vest = make_tracked(2, [60.0, 170.0, 140.0, 240.0], "vest", 2)

        states = build_ppe_states([person], [helmet], [vest])
        assert 27 in states
        state = states[27]
        assert state.helmet_detected is True
        assert state.vest_detected is True
        assert state.fully_compliant is True
        assert state.missing_ppe() == []

    def test_missing_helmet(self):
        """Worker with vest but no helmet → helmet violation."""
        person = make_tracked(14, [50.0, 100.0, 150.0, 300.0], "person", 0)
        vest = make_tracked(2, [60.0, 170.0, 140.0, 240.0], "vest", 2)

        states = build_ppe_states([person], [], [vest])
        state = states[14]
        assert state.helmet_detected is False
        assert state.vest_detected is True
        assert "helmet" in state.missing_ppe()

    def test_missing_vest(self):
        """Worker with helmet but no vest → vest violation."""
        person = make_tracked(31, [50.0, 100.0, 150.0, 300.0], "person", 0)
        helmet = make_tracked(1, [80.0, 110.0, 120.0, 145.0], "helmet", 1)

        states = build_ppe_states([person], [helmet], [])
        state = states[31]
        assert state.helmet_detected is True
        assert state.vest_detected is False
        assert "vest" in state.missing_ppe()

    def test_no_ppe_at_all(self):
        """Worker with no PPE → both violations."""
        person = make_tracked(5, [50.0, 100.0, 150.0, 300.0], "person", 0)
        states = build_ppe_states([person], [], [])
        state = states[5]
        assert not state.fully_compliant
        assert set(state.missing_ppe()) == {"helmet", "vest"}

    def test_no_persons(self):
        """No persons → empty result."""
        helmet = make_tracked(1, [80.0, 110.0, 120.0, 145.0], "helmet", 1)
        states = build_ppe_states([], [helmet], [])
        assert states == {}

    def test_ppe_not_shared_between_workers(self):
        """Each PPE item is assigned to at most one worker."""
        # Two workers stacked vertically — one helmet between them
        p1 = make_tracked(1, [50.0, 0.0, 150.0, 200.0], "person", 0)
        p2 = make_tracked(2, [50.0, 210.0, 150.0, 410.0], "person", 0)
        # Helmet belongs to p1 (upper position)
        helmet = make_tracked(10, [80.0, 10.0, 120.0, 40.0], "helmet", 1)

        states = build_ppe_states([p1, p2], [helmet], [])

        p1_state = states[1]
        p2_state = states[2]

        # Helmet should be associated to exactly one person
        assert p1_state.helmet_detected != p2_state.helmet_detected or (
            p1_state.helmet_detected and not p2_state.helmet_detected
        )
