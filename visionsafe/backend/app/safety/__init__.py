"""
VisionSafe Safety Intelligence Package.

Contains:
- ZoneEngine, point_in_polygon, ZoneStateMachine (Phase 3)
- PPEEngine (Phase 3)
- TemporalEngine, RawViolation, ConfirmedViolation, EndedViolation (Phase 3/6)
- SafetyRuleEngine, RuleConfig (Phase 4/7)
"""

from app.safety.zone_engine import ZoneEngine, point_in_polygon, ZoneStateMachine, ZoneTransition, ZoneTransitionType
from app.safety.ppe_engine import PPEEngine, PPEComplianceReport
from app.safety.temporal_engine import TemporalEngine, RawViolation, ConfirmedViolation, EndedViolation
from app.safety.rule_engine import (
    SafetyRuleEngine,
    RuleConfig,
    RULE_NO_HELMET,
    RULE_NO_VEST,
    RULE_RESTRICTED_ZONE_ENTRY,
    RULE_FORKLIFT_PROXIMITY,
    RULE_RESTRICTED_ZONE_PPE,
)

__all__ = [
    "ZoneEngine",
    "point_in_polygon",
    "ZoneStateMachine",
    "ZoneTransition",
    "ZoneTransitionType",
    "PPEEngine",
    "PPEComplianceReport",
    "TemporalEngine",
    "RawViolation",
    "ConfirmedViolation",
    "EndedViolation",
    "SafetyRuleEngine",
    "RuleConfig",
    "RULE_NO_HELMET",
    "RULE_NO_VEST",
    "RULE_RESTRICTED_ZONE_ENTRY",
    "RULE_FORKLIFT_PROXIMITY",
    "RULE_RESTRICTED_ZONE_PPE",
]
