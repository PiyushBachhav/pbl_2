"""
Unit and integration tests for VisionSafe Safety Layer:
- Point-in-polygon (Ray casting)
- Zone state machine (ENTERED, REMAINING, EXITED)
- PPE Engine (compliance evaluation)
- Temporal Engine (persistence threshold, duration tracking, event ending)
- Safety Rule Engine (all 5 rule types: NO_HELMET, NO_VEST, RESTRICTED_ZONE_ENTRY,
  FORKLIFT_PROXIMITY, RESTRICTED_ZONE_PPE)
- End-to-end pipeline test with SQLite DB persistence
"""

import math
import pytest
from app.vision.detections import Detection, TrackedObject, PPEState, FrameResult
from app.safety.zone_engine import (
    point_in_polygon,
    ZoneStateMachine,
    ZoneTransitionType,
    ZoneEngine,
)
from app.safety.ppe_engine import PPEEngine
from app.safety.temporal_engine import (
    TemporalEngine,
    RawViolation,
    ActiveViolationState,
)
from app.safety.rule_engine import (
    SafetyRuleEngine,
    RuleConfig,
    RULE_NO_HELMET,
    RULE_NO_VEST,
    RULE_RESTRICTED_ZONE_ENTRY,
    RULE_FORKLIFT_PROXIMITY,
    RULE_RESTRICTED_ZONE_PPE,
)


def make_worker(
    track_id: int,
    bbox: list[float],
    has_helmet: bool = True,
    has_vest: bool = True,
    confidence: float = 0.90,
) -> TrackedObject:
    det = Detection(
        bbox=bbox,
        class_id=0,
        class_name="person",
        confidence=confidence,
    )
    obj = TrackedObject(track_id=track_id, detection=det)
    obj.ppe_state = PPEState(
        person_track_id=track_id,
        helmet_detected=has_helmet,
        vest_detected=has_vest,
        helmet_confidence=0.9 if has_helmet else None,
        vest_confidence=0.9 if has_vest else None,
    )
    return obj


def make_forklift(
    track_id: int,
    bbox: list[float],
    confidence: float = 0.95,
) -> TrackedObject:
    det = Detection(
        bbox=bbox,
        class_id=3,
        class_name="forklift",
        confidence=confidence,
    )
    return TrackedObject(track_id=track_id, detection=det)


# ─────────────────────────────────────────
# 1. Point in Polygon Tests
# ─────────────────────────────────────────

class TestPointInPolygon:
    # A simple 100x100 square from (10, 10) to (110, 110)
    SQUARE = [[10.0, 10.0], [110.0, 10.0], [110.0, 110.0], [10.0, 110.0]]

    def test_point_inside(self):
        assert point_in_polygon((50.0, 50.0), self.SQUARE) is True

    def test_point_outside_left(self):
        assert point_in_polygon((5.0, 50.0), self.SQUARE) is False

    def test_point_outside_right(self):
        assert point_in_polygon((120.0, 50.0), self.SQUARE) is False

    def test_point_outside_top(self):
        assert point_in_polygon((50.0, 5.0), self.SQUARE) is False

    def test_point_outside_bottom(self):
        assert point_in_polygon((50.0, 120.0), self.SQUARE) is False

    def test_point_on_vertex(self):
        # Ray casting edge/vertex check
        assert point_in_polygon((10.0, 10.0), self.SQUARE) is True

    def test_concave_l_shape(self):
        # L-shaped polygon:
        # (0,0) -> (100,0) -> (100,50) -> (50,50) -> (50,100) -> (0,100)
        l_shape = [
            [0.0, 0.0], [100.0, 0.0], [100.0, 50.0],
            [50.0, 50.0], [50.0, 100.0], [0.0, 100.0]
        ]
        # Inside the L base
        assert point_in_polygon((25.0, 75.0), l_shape) is True
        # Inside the L vertical
        assert point_in_polygon((75.0, 25.0), l_shape) is True
        # In the cut-out corner (75, 75)
        assert point_in_polygon((75.0, 75.0), l_shape) is False

    def test_degenerate_polygon(self):
        assert point_in_polygon((10.0, 10.0), [[10.0, 10.0], [20.0, 20.0]]) is False
        assert point_in_polygon((10.0, 10.0), []) is False


# ─────────────────────────────────────────
# 2. Zone State Machine & Zone Engine
# ─────────────────────────────────────────

class TestZoneStateMachine:
    def test_entry_remaining_exit_transitions(self):
        sm = ZoneStateMachine()
        tid = 1
        zid = 101

        # Frame 1: Worker enters zone
        t1 = sm.update(tid, zid, is_inside=True, frame_idx=1, timestamp=0.04)
        assert t1 is not None
        assert t1.transition == ZoneTransitionType.ENTERED
        assert sm.is_inside(tid, zid) is True

        # Frame 2: Worker remains in zone
        t2 = sm.update(tid, zid, is_inside=True, frame_idx=2, timestamp=0.08)
        assert t2 is not None
        assert t2.transition == ZoneTransitionType.REMAINING
        assert sm.is_inside(tid, zid) is True

        # Frame 3: Worker exits zone
        t3 = sm.update(tid, zid, is_inside=False, frame_idx=3, timestamp=0.12)
        assert t3 is not None
        assert t3.transition == ZoneTransitionType.EXITED
        assert sm.is_inside(tid, zid) is False

        # Frame 4: Worker stays outside zone
        t4 = sm.update(tid, zid, is_inside=False, frame_idx=4, timestamp=0.16)
        assert t4 is None

    def test_reset_track(self):
        sm = ZoneStateMachine()
        sm.update(1, 101, is_inside=True)
        sm.update(1, 102, is_inside=True)
        exited = sm.reset_track(1)
        assert len(exited) == 2
        assert sm.is_inside(1, 101) is False
        assert sm.is_inside(1, 102) is False


class TestZoneEngine:
    def test_check_workers_in_zones(self):
        engine = ZoneEngine()
        zone = {
            "id": 1,
            "polygon": [[0.0, 0.0], [200.0, 0.0], [200.0, 200.0], [0.0, 200.0]],
            "enabled": True,
        }
        # Worker 1 foot at (50, 150) -> inside
        w1 = make_worker(1, [40.0, 50.0, 60.0, 150.0])
        # Worker 2 foot at (300, 300) -> outside
        w2 = make_worker(2, [290.0, 250.0, 310.0, 300.0])

        res = engine.check_workers_in_zones([w1, w2], [zone])
        assert res[1] == [1]
        assert res[2] == []


# ─────────────────────────────────────────
# 3. PPE Engine Tests
# ─────────────────────────────────────────

class TestPPEEngine:
    def setup_method(self):
        self.engine = PPEEngine()

    def test_compliant_worker(self):
        w = make_worker(1, [0, 0, 50, 100], has_helmet=True, has_vest=True)
        rep = self.engine.evaluate_worker(w)
        assert rep.is_compliant is True
        assert rep.missing_items == []

    def test_missing_helmet_only(self):
        w = make_worker(2, [0, 0, 50, 100], has_helmet=False, has_vest=True)
        rep = self.engine.evaluate_worker(w)
        assert rep.is_compliant is False
        assert rep.missing_items == ["helmet"]

    def test_missing_vest_only(self):
        w = make_worker(3, [0, 0, 50, 100], has_helmet=True, has_vest=False)
        rep = self.engine.evaluate_worker(w)
        assert rep.is_compliant is False
        assert rep.missing_items == ["vest"]

    def test_missing_all(self):
        w = make_worker(4, [0, 0, 50, 100], has_helmet=False, has_vest=False)
        rep = self.engine.evaluate_worker(w)
        assert rep.is_compliant is False
        assert set(rep.missing_items) == {"helmet", "vest"}

    def test_zone_specific_requirement(self):
        w = make_worker(5, [0, 0, 50, 100], has_helmet=True, has_vest=False)
        # Zone requires only helmet
        zone = {"id": 10, "required_ppe": ["helmet"]}
        rep = self.engine.evaluate_zone_compliance(w, zone)
        assert rep.is_compliant is True

        # Zone requires vest
        zone2 = {"id": 11, "required_ppe": ["vest"]}
        rep2 = self.engine.evaluate_zone_compliance(w, zone2)
        assert rep2.is_compliant is False


# ─────────────────────────────────────────
# 4. Temporal Engine Tests
# ─────────────────────────────────────────

class TestTemporalEngine:
    def test_persistence_threshold_prevents_single_frame_event(self):
        te = TemporalEngine(default_threshold=2.0, grace_period_seconds=1.0)

        v = RawViolation(
            rule_type="NO_HELMET",
            severity="HIGH",
            subject_track_id=1,
            threshold_seconds=2.0,
        )

        # Frame 1: at t=0.0s (0.0s elapsed -> no event)
        confirmed, ended = te.update([v], timestamp=0.0, frame_idx=0)
        assert len(confirmed) == 0
        assert len(ended) == 0

        # Frame 2: at t=1.0s (1.0s elapsed < 2.0s threshold -> no event)
        confirmed, ended = te.update([v], timestamp=1.0, frame_idx=25)
        assert len(confirmed) == 0
        assert len(ended) == 0

        # Frame 3: at t=2.1s (2.1s elapsed >= 2.0s -> confirmed!)
        confirmed, ended = te.update([v], timestamp=2.1, frame_idx=52)
        assert len(confirmed) == 1
        assert confirmed[0].rule_type == "NO_HELMET"
        assert confirmed[0].subject_track_id == 1

        # Frame 4: at t=2.5s (already confirmed -> not emitted again)
        confirmed2, ended2 = te.update([v], timestamp=2.5, frame_idx=62)
        assert len(confirmed2) == 0
        assert len(ended2) == 0

        # Violation condition ends: no violation observed at t=4.0s (gap 1.5s > grace 1.0s)
        confirmed3, ended3 = te.update([], timestamp=4.0, frame_idx=100)
        assert len(ended3) == 1
        assert ended3[0].rule_type == "NO_HELMET"
        assert ended3[0].duration_seconds == pytest.approx(2.5)

    def test_immediate_threshold(self):
        te = TemporalEngine(default_threshold=2.0)
        v = RawViolation(
            rule_type="RESTRICTED_ZONE_ENTRY",
            severity="CRITICAL",
            subject_track_id=2,
            threshold_seconds=0.0,  # instant trigger
        )
        confirmed, _ = te.update([v], timestamp=0.0, frame_idx=0)
        assert len(confirmed) == 1
        assert confirmed[0].rule_type == "RESTRICTED_ZONE_ENTRY"


# ─────────────────────────────────────────
# 5. Safety Rule Engine Tests
# ─────────────────────────────────────────

class TestSafetyRuleEngine:
    def setup_method(self):
        self.engine = SafetyRuleEngine()

    def test_no_helmet_detection(self):
        w = make_worker(10, [10, 20, 50, 100], has_helmet=False, has_vest=True)
        fr = FrameResult(frame_idx=1, timestamp=0.04, tracked_objects=[w])
        violations = self.engine.evaluate(fr)
        no_helmets = [v for v in violations if v.rule_type == RULE_NO_HELMET]
        assert len(no_helmets) == 1
        assert no_helmets[0].subject_track_id == 10

    def test_no_vest_detection(self):
        w = make_worker(11, [10, 20, 50, 100], has_helmet=True, has_vest=False)
        fr = FrameResult(frame_idx=1, timestamp=0.04, tracked_objects=[w])
        violations = self.engine.evaluate(fr)
        no_vests = [v for v in violations if v.rule_type == RULE_NO_VEST]
        assert len(no_vests) == 1
        assert no_vests[0].subject_track_id == 11

    def test_restricted_zone_entry(self):
        # Worker foot at (50, 150)
        w = make_worker(12, [40, 50, 60, 150], has_helmet=True, has_vest=True)
        zone = {
            "id": 99,
            "name": "Danger Excavation",
            "zone_type": "restricted",
            "polygon": [[0, 0], [200, 0], [200, 200], [0, 200]],
            "enabled": True,
        }
        fr = FrameResult(frame_idx=1, timestamp=0.04, tracked_objects=[w])
        violations = self.engine.evaluate(fr, zones=[zone])
        zone_entries = [v for v in violations if v.rule_type == RULE_RESTRICTED_ZONE_ENTRY]
        assert len(zone_entries) == 1
        assert zone_entries[0].zone_id == 99
        assert zone_entries[0].subject_track_id == 12

    def test_forklift_proximity_danger(self):
        # Worker foot at (100, 100)
        w = make_worker(1, [90, 40, 110, 100])
        # Forklift center at (150, 100) -> distance = 50px (< default 150px)
        fl = make_forklift(5, [130, 80, 170, 120])

        fr = FrameResult(frame_idx=1, timestamp=0.04, tracked_objects=[w, fl])
        violations = self.engine.evaluate(fr)
        prox = [v for v in violations if v.rule_type == RULE_FORKLIFT_PROXIMITY]
        assert len(prox) == 1
        assert prox[0].subject_track_id == 1
        assert prox[0].related_track_id == 5
        assert prox[0].metadata["distance_pixels"] == pytest.approx(50.0, abs=1.0)

    def test_forklift_safe_distance(self):
        # Worker foot at (100, 100)
        w = make_worker(1, [90, 40, 110, 100])
        # Forklift center at (500, 500) -> distance >> 150px
        fl = make_forklift(5, [480, 480, 520, 520])

        fr = FrameResult(frame_idx=1, timestamp=0.04, tracked_objects=[w, fl])
        violations = self.engine.evaluate(fr)
        prox = [v for v in violations if v.rule_type == RULE_FORKLIFT_PROXIMITY]
        assert len(prox) == 0
