"""Camera API routes."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import List

from app.db.database import get_db
from app.db.models import Camera

router = APIRouter(prefix="/cameras", tags=["cameras"])


@router.get("/", response_model=List[dict])
async def list_cameras(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Camera))
    cameras = result.scalars().all()
    return [
        {
            "id": c.id, "name": c.name, "location": c.location,
            "description": c.description, "enabled": c.enabled,
        }
        for c in cameras
    ]


@router.post("/", response_model=dict, status_code=201)
async def create_camera(payload: dict, db: AsyncSession = Depends(get_db)):
    camera = Camera(
        name=payload.get("name", "Camera"),
        location=payload.get("location"),
        description=payload.get("description"),
        enabled=payload.get("enabled", True),
    )
    db.add(camera)
    await db.flush()
    await db.refresh(camera)
    return {"id": camera.id, "name": camera.name}


@router.get("/{camera_id}", response_model=dict)
async def get_camera(camera_id: int, db: AsyncSession = Depends(get_db)):
    camera = await db.get(Camera, camera_id)
    if not camera:
        raise HTTPException(status_code=404, detail="Camera not found")
    return {"id": camera.id, "name": camera.name, "location": camera.location}
