"""
Zone point-in-polygon and state machine engine.

Determines whether tracked workers are inside designated zones
using the worker's foot point (TrackedObject.foot_x, foot_y)
and tracks state transitions (ENTERED, REMAINING, EXITED).
"""

from __future__ import annotations

import enum
import logging
from dataclasses import dataclass, field
from typing import Any, Sequence

from app.vision.detections import TrackedObject

logger = logging.getLogger(__name__)


class ZoneTransitionType(str, enum.Enum):
    ENTERED = "ENTERED"
    REMAINING = "REMAINING"
    EXITED = "EXITED"


@dataclass
class ZoneTransition:
    """Represents a worker transitioning state relative to a zone."""
    track_id: int
    zone_id: int
    transition: ZoneTransitionType
    frame_idx: int
    timestamp: float
    foot_point: tuple[float, float]


def point_in_polygon(point: tuple[float, float], polygon: Sequence[Sequence[float]]) -> bool:
    """
    Ray-casting algorithm (even-odd rule) to check if a 2D point is inside a polygon.

    Args:
        point: (x, y) coordinates
        polygon: list of [x, y] vertices

    Returns:
        True if point is strictly inside or on the boundary.
    """
    if len(polygon) < 3:
        return False

    x, y = point
    n = len(polygon)
    inside = False

    p1x, p1y = polygon[0]
    for i in range(1, n + 1):
        p2x, p2y = polygon[i % n]

        # Check if point is on an edge / vertex (optional exact boundary hit)
        if min(p1x, p2x) <= x <= max(p1x, p2x) and min(p1y, p2y) <= y <= max(p1y, p2y):
            # Check collinearity for line segment
            cross_product = (y - p1y) * (p2x - p1x) - (x - p1x) * (p2y - p1y)
            if abs(cross_product) < 1e-9:
                return True

        if y > min(p1y, p2y):
            if y <= max(p1y, p2y):
                if x <= max(p1x, p2x):
                    if p1y != p2y:
                        x_inters = (y - p1y) * (p2x - p1x) / (p2y - p1y) + p1x
                    if p1x == p2x or x <= x_inters:
                        inside = not inside

        p1x, p1y = p2x, p2y

    return inside


class ZoneStateMachine:
    """
    Tracks ENTERED / REMAINING / EXITED transitions per (track_id, zone_id).
    """

    def __init__(self):
        # Maps (track_id, zone_id) -> bool (is_currently_inside)
        self._inside_state: dict[tuple[int, int], bool] = {}

    def update(
        self,
        track_id: int,
        zone_id: int,
        is_inside: bool,
        frame_idx: int = 0,
        timestamp: float = 0.0,
        foot_point: tuple[float, float] = (0.0, 0.0),
    ) -> ZoneTransition | None:
        """
        Update state for a given track and zone.
        Returns a ZoneTransition event if a state transition occurred, or None.
        """
        key = (track_id, zone_id)
        was_inside = self._inside_state.get(key, False)

        transition_type: ZoneTransitionType | None = None

        if not was_inside and is_inside:
            transition_type = ZoneTransitionType.ENTERED
            self._inside_state[key] = True
        elif was_inside and is_inside:
            transition_type = ZoneTransitionType.REMAINING
        elif was_inside and not is_inside:
            transition_type = ZoneTransitionType.EXITED
            self._inside_state[key] = False

        if transition_type is not None:
            return ZoneTransition(
                track_id=track_id,
                zone_id=zone_id,
                transition=transition_type,
                frame_idx=frame_idx,
                timestamp=timestamp,
                foot_point=foot_point,
            )
        return None

    def reset_track(self, track_id: int) -> list[ZoneTransition]:
        """Call when a track is lost/expired to cleanly emit EXITED for all zones."""
        exited = []
        for (tid, zid), inside in list(self._inside_state.items()):
            if tid == track_id and inside:
                self._inside_state[(tid, zid)] = False
                exited.append(
                    ZoneTransition(
                        track_id=tid,
                        zone_id=zid,
                        transition=ZoneTransitionType.EXITED,
                        frame_idx=0,
                        timestamp=0.0,
                        foot_point=(0.0, 0.0),
                    )
                )
        return exited

    def is_inside(self, track_id: int, zone_id: int) -> bool:
        return self._inside_state.get((track_id, zone_id), False)


class ZoneEngine:
    """
    Evaluates worker positions relative to zones.
    """

    def __init__(self):
        self.state_machine = ZoneStateMachine()

    def check_workers_in_zones(
        self,
        persons: Sequence[TrackedObject],
        zones: Sequence[Any],
    ) -> dict[int, list[int]]:
        """
        Check which zones each worker is currently inside using their foot point.

        Args:
            persons: List of TrackedObject representing workers
            zones: List of Zone ORM objects or dicts with 'id' and 'polygon'

        Returns:
            dict mapping worker track_id -> list of zone_ids they occupy
        """
        results: dict[int, list[int]] = {p.track_id: [] for p in persons}

        for person in persons:
            foot_point = (person.foot_x, person.foot_y)
            for zone in zones:
                zid = zone["id"] if isinstance(zone, dict) else zone.id
                poly = zone["polygon"] if isinstance(zone, dict) else zone.polygon
                enabled = zone.get("enabled", True) if isinstance(zone, dict) else zone.enabled

                if not enabled or not poly or len(poly) < 3:
                    continue

                if point_in_polygon(foot_point, poly):
                    results[person.track_id].append(zid)

        return results

    def update_transitions(
        self,
        persons: Sequence[TrackedObject],
        zones: Sequence[Any],
        frame_idx: int = 0,
        timestamp: float = 0.0,
    ) -> list[ZoneTransition]:
        """
        Evaluates worker positions and updates the state machine,
        returning all transitions (ENTERED, REMAINING, EXITED) in this frame.
        """
        occupied_zones = self.check_workers_in_zones(persons, zones)
        transitions: list[ZoneTransition] = []

        active_zone_ids = [
            (z["id"] if isinstance(zone, dict) else z.id)
            for z in zones
            if (z.get("enabled", True) if isinstance(z, dict) else z.enabled)
        ]

        for person in persons:
            in_zones = set(occupied_zones.get(person.track_id, []))
            foot_pt = (person.foot_x, person.foot_y)

            for zid in active_zone_ids:
                is_in = zid in in_zones
                trans = self.state_machine.update(
                    track_id=person.track_id,
                    zone_id=zid,
                    is_inside=is_in,
                    frame_idx=frame_idx,
                    timestamp=timestamp,
                    foot_point=foot_pt,
                )
                if trans:
                    transitions.append(trans)

        return transitions
