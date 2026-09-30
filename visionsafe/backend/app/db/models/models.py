"""
SQLAlchemy ORM models for VisionSafe.

Table hierarchy:
  Camera → Videos, Zones, SafetyEvents
  Video  → ProcessingJob, Detections
  Zone   → SafetyEvents
  Rule   → SafetyEvents
  SafetyEvent → EventEvidence
"""

from __future__ import annotations

import enum
from datetime import datetime
from typing import Optional, List

from sqlalchemy import (
    Boolean, DateTime, Enum, Float, ForeignKey, Integer,
    JSON, String, Text, func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.database import Base


# ─────────────────────────────────────────
# Enums
# ─────────────────────────────────────────

class Severity(str, enum.Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class EventStatus(str, enum.Enum):
    OPEN = "OPEN"
    ACKNOWLEDGED = "ACKNOWLEDGED"
    RESOLVED = "RESOLVED"
    FALSE_POSITIVE = "FALSE_POSITIVE"


class JobStatus(str, enum.Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class ZoneType(str, enum.Enum):
    RESTRICTED = "restricted"
    PPE_REQUIRED = "ppe_required"
    FORKLIFT = "forklift"
    CAUTION = "caution"
    SAFE = "safe"


# ─────────────────────────────────────────
# Camera
# ─────────────────────────────────────────

class Camera(Base):
    __tablename__ = "cameras"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    location: Mapped[Optional[str]] = mapped_column(String(256))
    description: Mapped[Optional[str]] = mapped_column(Text)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    videos: Mapped[List["Video"]] = relationship("Video", back_populates="camera")
    zones: Mapped[List["Zone"]] = relationship("Zone", back_populates="camera")
    events: Mapped[List["SafetyEvent"]] = relationship("SafetyEvent", back_populates="camera")


# ─────────────────────────────────────────
# Video & Processing Job
# ─────────────────────────────────────────

class Video(Base):
    __tablename__ = "videos"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    camera_id: Mapped[Optional[int]] = mapped_column(ForeignKey("cameras.id"), nullable=True)
    filename: Mapped[str] = mapped_column(String(256), nullable=False)
    original_filename: Mapped[str] = mapped_column(String(256), nullable=False)
    file_path: Mapped[str] = mapped_column(String(512), nullable=False)
    file_size_bytes: Mapped[Optional[int]] = mapped_column(Integer)
    duration_seconds: Mapped[Optional[float]] = mapped_column(Float)
    fps: Mapped[Optional[float]] = mapped_column(Float)
    width: Mapped[Optional[int]] = mapped_column(Integer)
    height: Mapped[Optional[int]] = mapped_column(Integer)
    total_frames: Mapped[Optional[int]] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    camera: Mapped[Optional["Camera"]] = relationship("Camera", back_populates="videos")
    job: Mapped[Optional["ProcessingJob"]] = relationship(
        "ProcessingJob", back_populates="video", uselist=False
    )
    events: Mapped[List["SafetyEvent"]] = relationship("SafetyEvent", back_populates="video")


class ProcessingJob(Base):
    __tablename__ = "processing_jobs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    video_id: Mapped[int] = mapped_column(ForeignKey("videos.id"), nullable=False)
    status: Mapped[JobStatus] = mapped_column(
        Enum(JobStatus), default=JobStatus.PENDING, nullable=False
    )
    progress: Mapped[float] = mapped_column(Float, default=0.0)  # 0–100
    frames_processed: Mapped[int] = mapped_column(Integer, default=0)
    fps_achieved: Mapped[Optional[float]] = mapped_column(Float)
    error_message: Mapped[Optional[str]] = mapped_column(Text)
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    video: Mapped["Video"] = relationship("Video", back_populates="job")


# ─────────────────────────────────────────
# Zone
# ─────────────────────────────────────────

class Zone(Base):
    """
    A safety zone defined as a polygon on a camera view.

    polygon: list of [x, y] pixel coordinates stored as JSON.
    required_ppe: list of PPE class names required inside this zone.
    """
    __tablename__ = "zones"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    camera_id: Mapped[Optional[int]] = mapped_column(ForeignKey("cameras.id"), nullable=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    zone_type: Mapped[ZoneType] = mapped_column(Enum(ZoneType), default=ZoneType.RESTRICTED)
    severity: Mapped[Severity] = mapped_column(Enum(Severity), default=Severity.HIGH)
    polygon: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    required_ppe: Mapped[list] = mapped_column(JSON, default=list)  # e.g. ["helmet", "vest"]
    allowed_roles: Mapped[list] = mapped_column(JSON, default=list)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    color: Mapped[Optional[str]] = mapped_column(String(16), default="#FF4444")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    camera: Mapped[Optional["Camera"]] = relationship("Camera", back_populates="zones")
    events: Mapped[List["SafetyEvent"]] = relationship("SafetyEvent", back_populates="zone")


# ─────────────────────────────────────────
# Rule
# ─────────────────────────────────────────

class Rule(Base):
    """
    A configurable safety rule.

    The safety engine evaluates rules against tracked objects every frame.
    Rules are separate from YOLO — YOLO detects objects; rules determine danger.
    """
    __tablename__ = "rules"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    rule_type: Mapped[str] = mapped_column(String(64), nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    severity: Mapped[Severity] = mapped_column(Enum(Severity), default=Severity.HIGH)
    temporal_threshold_seconds: Mapped[float] = mapped_column(Float, default=2.0)
    conditions: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    events: Mapped[List["SafetyEvent"]] = relationship("SafetyEvent", back_populates="rule")


# ─────────────────────────────────────────
# Safety Event
# ─────────────────────────────────────────

class SafetyEvent(Base):
    """
    A confirmed safety violation event.

    An event is only created after temporal persistence is satisfied —
    a single-frame anomaly does not become an event.

    Fields:
      subject_track_id  — primary involved track (e.g. Worker #27)
      related_track_id  — secondary involved track (e.g. Forklift #3)
      started_at        — when the violation condition first appeared
      detected_at       — when the event was created (after persistence)
      ended_at          — when the violation condition disappeared
    """
    __tablename__ = "safety_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    camera_id: Mapped[Optional[int]] = mapped_column(ForeignKey("cameras.id"), nullable=True)
    video_id: Mapped[Optional[int]] = mapped_column(ForeignKey("videos.id"), nullable=True)
    rule_id: Mapped[Optional[int]] = mapped_column(ForeignKey("rules.id"), nullable=True)
    zone_id: Mapped[Optional[int]] = mapped_column(ForeignKey("zones.id"), nullable=True)

    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    severity: Mapped[Severity] = mapped_column(Enum(Severity), nullable=False)
    status: Mapped[EventStatus] = mapped_column(Enum(EventStatus), default=EventStatus.OPEN)

    subject_track_id: Mapped[Optional[int]] = mapped_column(Integer)
    related_track_id: Mapped[Optional[int]] = mapped_column(Integer)

    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    detected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    ended_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    duration_seconds: Mapped[Optional[float]] = mapped_column(Float)

    confidence: Mapped[Optional[float]] = mapped_column(Float)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    evidence_frame_path: Mapped[Optional[str]] = mapped_column(String(512))

    # Flexible metadata: zone polygon, PPE state, distances, etc.
    event_metadata: Mapped[dict] = mapped_column(JSON, default=dict)

    camera: Mapped[Optional["Camera"]] = relationship("Camera", back_populates="events")
    video: Mapped[Optional["Video"]] = relationship("Video", back_populates="events")
    rule: Mapped[Optional["Rule"]] = relationship("Rule", back_populates="events")
    zone: Mapped[Optional["Zone"]] = relationship("Zone", back_populates="events")
    evidence: Mapped[List["EventEvidence"]] = relationship("EventEvidence", back_populates="event")


class EventEvidence(Base):
    """Annotated frame saved as evidence when a safety event is created."""
    __tablename__ = "event_evidence"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    event_id: Mapped[int] = mapped_column(ForeignKey("safety_events.id"), nullable=False)
    frame_path: Mapped[str] = mapped_column(String(512), nullable=False)
    frame_number: Mapped[Optional[int]] = mapped_column(Integer)
    timestamp: Mapped[Optional[float]] = mapped_column(Float)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    event: Mapped["SafetyEvent"] = relationship("SafetyEvent", back_populates="evidence")
