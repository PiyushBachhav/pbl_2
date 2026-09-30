"""Safety events API — list, filter, acknowledge, resolve."""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import Optional
from app.db.database import get_db
from app.db.models import SafetyEvent, EventStatus, Severity

router = APIRouter(prefix="/events", tags=["events"])


@router.get("/", response_model=list[dict])
async def list_events(
    severity: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    event_type: Optional[str] = Query(None),
    camera_id: Optional[int] = Query(None),
    zone_id: Optional[int] = Query(None),
    limit: int = Query(100, le=500),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
):
    q = select(SafetyEvent).order_by(SafetyEvent.detected_at.desc()).limit(limit).offset(offset)

    if severity:
        q = q.where(SafetyEvent.severity == Severity(severity))
    if status:
        q = q.where(SafetyEvent.status == EventStatus(status))
    if event_type:
        q = q.where(SafetyEvent.event_type == event_type)
    if camera_id:
        q = q.where(SafetyEvent.camera_id == camera_id)
    if zone_id:
        q = q.where(SafetyEvent.zone_id == zone_id)

    result = await db.execute(q)
    events = result.scalars().all()
    return [_event_dict(e) for e in events]


@router.get("/{event_id}", response_model=dict)
async def get_event(event_id: int, db: AsyncSession = Depends(get_db)):
    event = await db.get(SafetyEvent, event_id)
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")
    return _event_dict(event)


@router.patch("/{event_id}", response_model=dict)
async def update_event_status(
    event_id: int,
    payload: dict,
    db: AsyncSession = Depends(get_db),
):
    """Acknowledge, resolve, or mark false positive."""
    event = await db.get(SafetyEvent, event_id)
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")

    new_status = payload.get("status")
    if new_status:
        try:
            event.status = EventStatus(new_status)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid status: {new_status}")

    return _event_dict(event)


def _event_dict(e: SafetyEvent) -> dict:
    return {
        "id": e.id,
        "event_type": e.event_type,
        "severity": e.severity.value,
        "status": e.status.value,
        "subject_track_id": e.subject_track_id,
        "related_track_id": e.related_track_id,
        "camera_id": e.camera_id,
        "video_id": e.video_id,
        "zone_id": e.zone_id,
        "rule_id": e.rule_id,
        "started_at": e.started_at.isoformat() if e.started_at else None,
        "detected_at": e.detected_at.isoformat() if e.detected_at else None,
        "ended_at": e.ended_at.isoformat() if e.ended_at else None,
        "duration_seconds": e.duration_seconds,
        "confidence": e.confidence,
        "description": e.description,
        "evidence_frame_path": e.evidence_frame_path,
        "metadata": e.event_metadata,
    }
