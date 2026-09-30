"""Analytics API — aggregated safety statistics."""
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, text
from app.db.database import get_db
from app.db.models import SafetyEvent, Severity, EventStatus

router = APIRouter(prefix="/analytics", tags=["analytics"])


@router.get("/summary", response_model=dict)
async def get_summary(db: AsyncSession = Depends(get_db)):
    """Dashboard summary card data."""
    total_q = await db.execute(select(func.count(SafetyEvent.id)))
    total = total_q.scalar() or 0

    open_q = await db.execute(
        select(func.count(SafetyEvent.id)).where(SafetyEvent.status == EventStatus.OPEN)
    )
    open_events = open_q.scalar() or 0

    high_q = await db.execute(
        select(func.count(SafetyEvent.id)).where(
            SafetyEvent.severity.in_([Severity.HIGH, Severity.CRITICAL])
        )
    )
    high_events = high_q.scalar() or 0

    return {
        "total_events": total,
        "open_events": open_events,
        "high_critical_events": high_events,
        "resolved_events": total - open_events,
    }


@router.get("/violations", response_model=list[dict])
async def get_violations_by_type(db: AsyncSession = Depends(get_db)):
    """Event count grouped by event_type."""
    result = await db.execute(
        select(SafetyEvent.event_type, func.count(SafetyEvent.id).label("count"))
        .group_by(SafetyEvent.event_type)
        .order_by(func.count(SafetyEvent.id).desc())
    )
    rows = result.all()
    return [{"event_type": r[0], "count": r[1]} for r in rows]
