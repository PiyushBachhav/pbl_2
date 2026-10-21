"""
Temporal violation engine for VisionSafe.

Accumulates violation observations over time/frames to ensure
that safety violations persist for a configurable duration threshold
(e.g., 2.0 seconds) before raising a permanent SafetyEvent.
This eliminates single-frame flickers and false positives.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Optional

logger = logging.getLogger(__name__)


@dataclass
class RawViolation:
    """An instantaneous violation candidate detected in a single frame."""
    rule_type: str
    severity: str
    subject_track_id: Optional[int] = None
    related_track_id: Optional[int] = None
    zone_id: Optional[int] = None
    rule_id: Optional[int] = None
    confidence: float = 1.0
    description: str = ""
    threshold_seconds: float = 2.0
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def key(self) -> tuple:
        """Unique key identifying the violation entity/condition."""
        return (
            self.rule_type,
            self.subject_track_id,
            self.related_track_id,
            self.zone_id,
        )


@dataclass
class ActiveViolationState:
    """Internal state tracking an ongoing violation condition."""
    raw: RawViolation
    first_timestamp: float
    last_timestamp: float
    first_frame_idx: int
    last_frame_idx: int
    frame_count: int = 1
    is_confirmed: bool = False
    is_closed: bool = False
    db_event_id: Optional[int] = None

    @property
    def duration_seconds(self) -> float:
        return max(0.0, self.last_timestamp - self.first_timestamp)


@dataclass
class ConfirmedViolation:
    """Emitted once a violation reaches its persistence threshold."""
    state: ActiveViolationState
    rule_type: str
    severity: str
    subject_track_id: Optional[int]
    related_track_id: Optional[int]
    zone_id: Optional[int]
    rule_id: Optional[int]
    confidence: float
    description: str
    started_at: float
    detected_at: float
    first_frame_idx: int
    detected_frame_idx: int
    metadata: dict[str, Any]


@dataclass
class EndedViolation:
    """Emitted when a previously confirmed violation condition ceases."""
    state: ActiveViolationState
    db_event_id: Optional[int]
    subject_track_id: Optional[int]
    rule_type: str
    started_at: float
    ended_at: float
    duration_seconds: float


class TemporalEngine:
    """
    Manages temporal persistence and life-cycle of safety violations.

    Parameters:
        default_threshold: Default seconds a violation must persist to confirm.
        grace_period_seconds: Maximum time gap without violation before closing it.
    """

    def __init__(
        self,
        default_threshold: float = 2.0,
        grace_period_seconds: float = 1.0,
    ):
        self.default_threshold = default_threshold
        self.grace_period_seconds = grace_period_seconds
        # Maps violation key -> ActiveViolationState
        self._active: dict[tuple, ActiveViolationState] = {}

    def update(
        self,
        current_violations: list[RawViolation],
        timestamp: float,
        frame_idx: int,
    ) -> tuple[list[ConfirmedViolation], list[EndedViolation]]:
        """
        Ingest current frame violations and evaluate state transitions.

        Returns:
            newly_confirmed: Violations that just crossed their temporal threshold
            ended_violations: Previously confirmed violations that have stopped
        """
        newly_confirmed: list[ConfirmedViolation] = []
        ended_violations: list[EndedViolation] = []

        seen_keys = set()

        for raw in current_violations:
            key = raw.key
            seen_keys.add(key)
            threshold = raw.threshold_seconds if raw.threshold_seconds is not None else self.default_threshold

            if key not in self._active:
                # Start tracking new candidate
                state = ActiveViolationState(
                    raw=raw,
                    first_timestamp=timestamp,
                    last_timestamp=timestamp,
                    first_frame_idx=frame_idx,
                    last_frame_idx=frame_idx,
                    frame_count=1,
                    is_confirmed=False,
                )
                self._active[key] = state

                # If threshold is 0.0 or instant, confirm immediately
                if threshold <= 0.0:
                    state.is_confirmed = True
                    newly_confirmed.append(self._create_confirmed(state, timestamp, frame_idx))
            else:
                # Update existing state
                state = self._active[key]
                state.last_timestamp = timestamp
                state.last_frame_idx = frame_idx
                state.frame_count += 1
                state.raw = raw  # update metadata with freshest info

                # Check if threshold crossed
                if not state.is_confirmed and state.duration_seconds >= threshold:
                    state.is_confirmed = True
                    newly_confirmed.append(self._create_confirmed(state, timestamp, frame_idx))

        # Check for expired/ended violations
        keys_to_remove = []
        for key, state in self._active.items():
            if key not in seen_keys:
                gap = timestamp - state.last_timestamp
                if gap > self.grace_period_seconds:
                    # Condition ended
                    if state.is_confirmed:
                        ended_violations.append(
                            EndedViolation(
                                state=state,
                                db_event_id=state.db_event_id,
                                subject_track_id=state.raw.subject_track_id,
                                rule_type=state.raw.rule_type,
                                started_at=state.first_timestamp,
                                ended_at=state.last_timestamp,
                                duration_seconds=state.duration_seconds,
                            )
                        )
                    keys_to_remove.append(key)

        for k in keys_to_remove:
            del self._active[k]

        return newly_confirmed, ended_violations

    def flush_all(
        self,
        final_timestamp: float,
    ) -> list[EndedViolation]:
        """Flush remaining confirmed violations at end of video/stream."""
        ended = []
        for state in self._active.values():
            if state.is_confirmed:
                ended.append(
                    EndedViolation(
                        state=state,
                        db_event_id=state.db_event_id,
                        subject_track_id=state.raw.subject_track_id,
                        rule_type=state.raw.rule_type,
                        started_at=state.first_timestamp,
                        ended_at=state.last_timestamp,
                        duration_seconds=state.duration_seconds,
                    )
                )
        self._active.clear()
        return ended

    def _create_confirmed(
        self,
        state: ActiveViolationState,
        detected_timestamp: float,
        detected_frame_idx: int,
    ) -> ConfirmedViolation:
        raw = state.raw
        return ConfirmedViolation(
            state=state,
            rule_type=raw.rule_type,
            severity=raw.severity,
            subject_track_id=raw.subject_track_id,
            related_track_id=raw.related_track_id,
            zone_id=raw.zone_id,
            rule_id=raw.rule_id,
            confidence=raw.confidence,
            description=raw.description,
            started_at=state.first_timestamp,
            detected_at=detected_timestamp,
            first_frame_idx=state.first_frame_idx,
            detected_frame_idx=detected_frame_idx,
            metadata=raw.metadata,
        )
