"""
Safety Rule Engine for VisionSafe.

Evaluates configured safety rules against frame detection results,
zone memberships, and proximity calculations to produce raw safety violations.
YOLO detects objects; this engine determines violations.
"""

from __future__ import annotations

import math
import logging
from dataclasses import dataclass, field
from typing import Any, Sequence

from app.vision.detections import FrameResult, TrackedObject
from app.safety.temporal_engine import RawViolation
from app.safety.zone_engine import ZoneEngine
from app.safety.ppe_engine import PPEEngine

logger = logging.getLogger(__name__)


# Standard Rule Types
RULE_NO_HELMET = "NO_HELMET"
RULE_NO_VEST = "NO_VEST"
RULE_RESTRICTED_ZONE_ENTRY = "RESTRICTED_ZONE_ENTRY"
RULE_FORKLIFT_PROXIMITY = "FORKLIFT_PROXIMITY"
RULE_RESTRICTED_ZONE_PPE = "RESTRICTED_ZONE_PPE"

DEFAULT_PROXIMITY_THRESHOLD = 150.0  # pixels in image-space


@dataclass
class RuleConfig:
    """In-memory representation of a safety rule."""
    id: int | None
    name: str
    rule_type: str
    severity: str = "HIGH"
    enabled: bool = True
    temporal_threshold_seconds: float = 2.0
    conditions: dict[str, Any] = field(default_factory=dict)


class SafetyRuleEngine:
    """
    Evaluates safety rules on each frame result.
    """

    def __init__(
        self,
        rules: Sequence[Any] | None = None,
        zone_engine: ZoneEngine | None = None,
        ppe_engine: PPEEngine | None = None,
    ):
        self.zone_engine = zone_engine or ZoneEngine()
        self.ppe_engine = ppe_engine or PPEEngine()
        self.rules: list[RuleConfig] = []
        if rules:
            self.set_rules(rules)
        else:
            self._set_default_rules()

    def set_rules(self, rules: Sequence[Any]) -> None:
        """Load rules from ORM objects or dicts."""
        self.rules = []
        for r in rules:
            if isinstance(r, dict):
                self.rules.append(
                    RuleConfig(
                        id=r.get("id"),
                        name=r.get("name", "Rule"),
                        rule_type=r.get("rule_type", ""),
                        severity=r.get("severity", "HIGH"),
                        enabled=r.get("enabled", True),
                        temporal_threshold_seconds=float(r.get("temporal_threshold_seconds", 2.0)),
                        conditions=r.get("conditions", {}) or {},
                    )
                )
            else:
                self.rules.append(
                    RuleConfig(
                        id=getattr(r, "id", None),
                        name=getattr(r, "name", "Rule"),
                        rule_type=getattr(r, "rule_type", ""),
                        severity=getattr(r, "severity", "HIGH").value if hasattr(getattr(r, "severity", None), "value") else str(getattr(r, "severity", "HIGH")),
                        enabled=getattr(r, "enabled", True),
                        temporal_threshold_seconds=float(getattr(r, "temporal_threshold_seconds", 2.0)),
                        conditions=getattr(r, "conditions", {}) or {},
                    )
                )

    def _set_default_rules(self) -> None:
        """Default safety rules if none configured in database."""
        self.rules = [
            RuleConfig(
                id=1,
                name="Hardhat Required",
                rule_type=RULE_NO_HELMET,
                severity="HIGH",
                enabled=True,
                temporal_threshold_seconds=1.5,
            ),
            RuleConfig(
                id=2,
                name="Safety Vest Required",
                rule_type=RULE_NO_VEST,
                severity="HIGH",
                enabled=True,
                temporal_threshold_seconds=1.5,
            ),
            RuleConfig(
                id=3,
                name="Restricted Zone Breach",
                rule_type=RULE_RESTRICTED_ZONE_ENTRY,
                severity="CRITICAL",
                enabled=True,
                temporal_threshold_seconds=1.0,
            ),
            RuleConfig(
                id=4,
                name="Forklift Proximity Danger",
                rule_type=RULE_FORKLIFT_PROXIMITY,
                severity="CRITICAL",
                enabled=True,
                temporal_threshold_seconds=0.5,
                conditions={"proximity_threshold_pixels": DEFAULT_PROXIMITY_THRESHOLD},
            ),
            RuleConfig(
                id=5,
                name="Zone PPE Compliance",
                rule_type=RULE_RESTRICTED_ZONE_PPE,
                severity="HIGH",
                enabled=True,
                temporal_threshold_seconds=1.5,
            ),
        ]

    def evaluate(
        self,
        frame_result: FrameResult,
        zones: Sequence[Any] = (),
    ) -> list[RawViolation]:
        """
        Evaluate all active rules on a FrameResult.

        Args:
            frame_result: detections and tracked objects for current frame
            zones: list of active Zone objects / dicts

        Returns:
            list of RawViolation detected in this frame
        """
        violations: list[RawViolation] = []

        tracked = frame_result.tracked_objects
        persons = [t for t in tracked if t.class_name == "person" and t.track_id >= 0]
        forklifts = [t for t in tracked if t.class_name == "forklift" and t.track_id >= 0]

        # Calculate worker zone memberships
        worker_zones = self.zone_engine.check_workers_in_zones(persons, zones)

        zone_dict = {
            (z["id"] if isinstance(z, dict) else z.id): z
            for z in zones
        }

        # Filter enabled rules
        active_rules = [r for r in self.rules if r.enabled]

        for rule in active_rules:
            if rule.rule_type == RULE_NO_HELMET:
                violations.extend(self._check_no_helmet(rule, persons))
            elif rule.rule_type == RULE_NO_VEST:
                violations.extend(self._check_no_vest(rule, persons))
            elif rule.rule_type == RULE_RESTRICTED_ZONE_ENTRY:
                violations.extend(self._check_restricted_zone_entry(rule, persons, worker_zones, zone_dict))
            elif rule.rule_type == RULE_FORKLIFT_PROXIMITY:
                violations.extend(self._check_forklift_proximity(rule, persons, forklifts))
            elif rule.rule_type == RULE_RESTRICTED_ZONE_PPE:
                violations.extend(self._check_zone_ppe(rule, persons, worker_zones, zone_dict))

        return violations

    def _check_no_helmet(self, rule: RuleConfig, persons: list[TrackedObject]) -> list[RawViolation]:
        out = []
        for person in persons:
            state = person.ppe_state
            if state and not state.helmet_detected:
                out.append(
                    RawViolation(
                        rule_type=RULE_NO_HELMET,
                        severity=rule.severity,
                        subject_track_id=person.track_id,
                        rule_id=rule.id,
                        confidence=round(person.confidence, 2),
                        description=f"Worker #{person.track_id} detected without required hardhat/helmet.",
                        threshold_seconds=rule.temporal_threshold_seconds,
                        metadata={
                            "bbox": person.bbox,
                            "foot": [person.foot_x, person.foot_y],
                        },
                    )
                )
        return out

    def _check_no_vest(self, rule: RuleConfig, persons: list[TrackedObject]) -> list[RawViolation]:
        out = []
        for person in persons:
            state = person.ppe_state
            if state and not state.vest_detected:
                out.append(
                    RawViolation(
                        rule_type=RULE_NO_VEST,
                        severity=rule.severity,
                        subject_track_id=person.track_id,
                        rule_id=rule.id,
                        confidence=round(person.confidence, 2),
                        description=f"Worker #{person.track_id} detected without high-visibility safety vest.",
                        threshold_seconds=rule.temporal_threshold_seconds,
                        metadata={
                            "bbox": person.bbox,
                            "foot": [person.foot_x, person.foot_y],
                        },
                    )
                )
        return out

    def _check_restricted_zone_entry(
        self,
        rule: RuleConfig,
        persons: list[TrackedObject],
        worker_zones: dict[int, list[int]],
        zone_dict: dict[int, Any],
    ) -> list[RawViolation]:
        out = []
        for person in persons:
            zone_ids = worker_zones.get(person.track_id, [])
            for zid in zone_ids:
                z = zone_dict.get(zid)
                if not z:
                    continue
                ztype = z.get("zone_type", "") if isinstance(z, dict) else (
                    z.zone_type.value if hasattr(z.zone_type, "value") else str(z.zone_type)
                )
                zname = z.get("name", f"Zone #{zid}") if isinstance(z, dict) else z.name

                if ztype in ("restricted", "forklift"):
                    out.append(
                        RawViolation(
                            rule_type=RULE_RESTRICTED_ZONE_ENTRY,
                            severity=rule.severity,
                            subject_track_id=person.track_id,
                            zone_id=zid,
                            rule_id=rule.id,
                            confidence=round(person.confidence, 2),
                            description=f"Worker #{person.track_id} entered restricted exclusion zone '{zname}'.",
                            threshold_seconds=rule.temporal_threshold_seconds,
                            metadata={
                                "zone_id": zid,
                                "zone_name": zname,
                                "zone_type": ztype,
                                "foot": [person.foot_x, person.foot_y],
                            },
                        )
                    )
        return out

    def _check_forklift_proximity(
        self,
        rule: RuleConfig,
        persons: list[TrackedObject],
        forklifts: list[TrackedObject],
    ) -> list[RawViolation]:
        out = []
        thresh = float(rule.conditions.get("proximity_threshold_pixels", DEFAULT_PROXIMITY_THRESHOLD))

        for person in persons:
            px, py = person.foot_x, person.foot_y
            for fl in forklifts:
                # Forklift center or bottom
                fx1, fy1, fx2, fy2 = fl.bbox
                fcx = (fx1 + fx2) / 2.0
                fcy = (fy1 + fy2) / 2.0

                dist = math.hypot(px - fcx, py - fcy)
                if dist <= thresh:
                    out.append(
                        RawViolation(
                            rule_type=RULE_FORKLIFT_PROXIMITY,
                            severity=rule.severity,
                            subject_track_id=person.track_id,
                            related_track_id=fl.track_id,
                            rule_id=rule.id,
                            confidence=round(min(person.confidence, fl.confidence), 2),
                            description=(
                                f"Dangerous proximity ({dist:.1f}px < {thresh:.0f}px) "
                                f"between Worker #{person.track_id} and Forklift #{fl.track_id}."
                            ),
                            threshold_seconds=rule.temporal_threshold_seconds,
                            metadata={
                                "distance_pixels": round(dist, 1),
                                "threshold_pixels": thresh,
                                "person_foot": [px, py],
                                "forklift_center": [fcx, fcy],
                            },
                        )
                    )
        return out

    def _check_zone_ppe(
        self,
        rule: RuleConfig,
        persons: list[TrackedObject],
        worker_zones: dict[int, list[int]],
        zone_dict: dict[int, Any],
    ) -> list[RawViolation]:
        out = []
        for person in persons:
            zone_ids = worker_zones.get(person.track_id, [])
            for zid in zone_ids:
                z = zone_dict.get(zid)
                if not z:
                    continue
                ztype = z.get("zone_type", "") if isinstance(z, dict) else (
                    z.zone_type.value if hasattr(z.zone_type, "value") else str(z.zone_type)
                )
                if ztype in ("ppe_required", "caution", "restricted"):
                    report = self.ppe_engine.evaluate_zone_compliance(person, z)
                    if not report.is_compliant:
                        zname = z.get("name", f"Zone #{zid}") if isinstance(z, dict) else z.name
                        missing_str = ", ".join(report.missing_items)
                        out.append(
                            RawViolation(
                                rule_type=RULE_RESTRICTED_ZONE_PPE,
                                severity=rule.severity,
                                subject_track_id=person.track_id,
                                zone_id=zid,
                                rule_id=rule.id,
                                confidence=round(person.confidence, 2),
                                description=(
                                    f"Worker #{person.track_id} in '{zname}' missing mandatory PPE: {missing_str}."
                                ),
                                threshold_seconds=rule.temporal_threshold_seconds,
                                metadata={
                                    "zone_id": zid,
                                    "zone_name": zname,
                                    "missing_items": report.missing_items,
                                    "has_helmet": report.has_helmet,
                                    "has_vest": report.has_vest,
                                },
                            )
                        )
        return out
