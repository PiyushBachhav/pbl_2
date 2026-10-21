"""
PPE compliance evaluation engine.

Evaluates tracked worker PPE states against zone requirements
and global safety compliance policies.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Sequence

from app.vision.detections import TrackedObject, PPEState

logger = logging.getLogger(__name__)


@dataclass
class PPEComplianceReport:
    """Detailed PPE compliance status for a tracked worker."""
    track_id: int
    has_helmet: bool
    has_vest: bool
    missing_items: list[str]
    is_compliant: bool
    zone_id: int | None = None


class PPEEngine:
    """Evaluates PPE compliance per worker and per zone requirements."""

    def evaluate_worker(
        self,
        worker: TrackedObject,
        required_ppe: Sequence[str] = ("helmet", "vest"),
        zone_id: int | None = None,
    ) -> PPEComplianceReport:
        """
        Evaluate if a worker meets the required PPE list.

        Args:
            worker: TrackedObject (class_name == "person")
            required_ppe: list of required item names (e.g. ["helmet", "vest"])
            zone_id: optional zone id context
        """
        ppe: PPEState | None = worker.ppe_state
        has_helmet = ppe.helmet_detected if ppe else False
        has_vest = ppe.vest_detected if ppe else False

        missing = []
        for item in required_ppe:
            item_lower = item.lower().strip()
            if item_lower == "helmet" and not has_helmet:
                missing.append("helmet")
            elif item_lower == "vest" and not has_vest:
                missing.append("vest")

        return PPEComplianceReport(
            track_id=worker.track_id,
            has_helmet=has_helmet,
            has_vest=has_vest,
            missing_items=missing,
            is_compliant=(len(missing) == 0),
            zone_id=zone_id,
        )

    def evaluate_zone_compliance(
        self,
        worker: TrackedObject,
        zone: Any,
    ) -> PPEComplianceReport:
        """
        Evaluate worker compliance against a specific zone's required_ppe list.
        """
        zid = zone["id"] if isinstance(zone, dict) else zone.id
        req_ppe = zone.get("required_ppe", []) if isinstance(zone, dict) else zone.required_ppe
        if not req_ppe:
            req_ppe = ["helmet", "vest"]

        return self.evaluate_worker(worker, required_ppe=req_ppe, zone_id=zid)
