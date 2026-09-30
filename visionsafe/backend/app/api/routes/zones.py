"""Zones CRUD API."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.db.database import get_db
from app.db.models import Zone, ZoneType, Severity

router = APIRouter(prefix="/zones", tags=["zones"])


@router.get("/", response_model=list[dict])
async def list_zones(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Zone))
    zones = result.scalars().all()
    return [_zone_dict(z) for z in zones]


@router.post("/", response_model=dict, status_code=201)
async def create_zone(payload: dict, db: AsyncSession = Depends(get_db)):
    polygon = payload.get("polygon", [])
    if len(polygon) < 3:
        raise HTTPException(status_code=400, detail="Zone polygon must have at least 3 points.")

    zone = Zone(
        name=payload.get("name", "Zone"),
        description=payload.get("description"),
        camera_id=payload.get("camera_id"),
        zone_type=ZoneType(payload.get("zone_type", "restricted")),
        severity=Severity(payload.get("severity", "HIGH")),
        polygon=polygon,
        required_ppe=payload.get("required_ppe", []),
        allowed_roles=payload.get("allowed_roles", []),
        enabled=payload.get("enabled", True),
        color=payload.get("color", "#FF4444"),
    )
    db.add(zone)
    await db.flush()
    await db.refresh(zone)
    return _zone_dict(zone)


@router.get("/{zone_id}", response_model=dict)
async def get_zone(zone_id: int, db: AsyncSession = Depends(get_db)):
    zone = await db.get(Zone, zone_id)
    if not zone:
        raise HTTPException(status_code=404, detail="Zone not found")
    return _zone_dict(zone)


@router.put("/{zone_id}", response_model=dict)
async def update_zone(zone_id: int, payload: dict, db: AsyncSession = Depends(get_db)):
    zone = await db.get(Zone, zone_id)
    if not zone:
        raise HTTPException(status_code=404, detail="Zone not found")

    for key, val in payload.items():
        if hasattr(zone, key) and key not in ("id", "created_at"):
            if key == "zone_type":
                val = ZoneType(val)
            elif key == "severity":
                val = Severity(val)
            setattr(zone, key, val)

    return _zone_dict(zone)


@router.delete("/{zone_id}", status_code=204)
async def delete_zone(zone_id: int, db: AsyncSession = Depends(get_db)):
    zone = await db.get(Zone, zone_id)
    if not zone:
        raise HTTPException(status_code=404, detail="Zone not found")
    await db.delete(zone)


def _zone_dict(z: Zone) -> dict:
    return {
        "id": z.id,
        "name": z.name,
        "description": z.description,
        "camera_id": z.camera_id,
        "zone_type": z.zone_type.value,
        "severity": z.severity.value,
        "polygon": z.polygon,
        "required_ppe": z.required_ppe,
        "allowed_roles": z.allowed_roles,
        "enabled": z.enabled,
        "color": z.color,
    }
