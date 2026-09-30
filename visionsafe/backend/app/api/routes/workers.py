"""Workers (tracked persons) API — query track history."""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.database import get_db

router = APIRouter(prefix="/workers", tags=["workers"])


@router.get("/", response_model=list[dict])
async def list_workers(db: AsyncSession = Depends(get_db)):
    """
    V1: Workers are identified by track IDs only.
    No biometric identification is implemented.
    This endpoint returns a placeholder — real data comes after Phase 8.
    """
    return []
