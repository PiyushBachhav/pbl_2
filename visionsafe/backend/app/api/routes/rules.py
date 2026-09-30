"""Rules CRUD API."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.db.database import get_db
from app.db.models import Rule, Severity

router = APIRouter(prefix="/rules", tags=["rules"])


@router.get("/", response_model=list[dict])
async def list_rules(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Rule))
    rules = result.scalars().all()
    return [_rule_dict(r) for r in rules]


@router.post("/", response_model=dict, status_code=201)
async def create_rule(payload: dict, db: AsyncSession = Depends(get_db)):
    rule = Rule(
        name=payload.get("name", "Rule"),
        description=payload.get("description"),
        rule_type=payload.get("rule_type", "NO_HELMET"),
        enabled=payload.get("enabled", True),
        severity=Severity(payload.get("severity", "HIGH")),
        temporal_threshold_seconds=payload.get("temporal_threshold_seconds", 2.0),
        conditions=payload.get("conditions", {}),
    )
    db.add(rule)
    await db.flush()
    await db.refresh(rule)
    return _rule_dict(rule)


@router.get("/{rule_id}", response_model=dict)
async def get_rule(rule_id: int, db: AsyncSession = Depends(get_db)):
    rule = await db.get(Rule, rule_id)
    if not rule:
        raise HTTPException(status_code=404, detail="Rule not found")
    return _rule_dict(rule)


@router.put("/{rule_id}", response_model=dict)
async def update_rule(rule_id: int, payload: dict, db: AsyncSession = Depends(get_db)):
    rule = await db.get(Rule, rule_id)
    if not rule:
        raise HTTPException(status_code=404, detail="Rule not found")
    for key, val in payload.items():
        if hasattr(rule, key) and key not in ("id", "created_at"):
            if key == "severity":
                val = Severity(val)
            setattr(rule, key, val)
    return _rule_dict(rule)


def _rule_dict(r: Rule) -> dict:
    return {
        "id": r.id,
        "name": r.name,
        "description": r.description,
        "rule_type": r.rule_type,
        "enabled": r.enabled,
        "severity": r.severity.value,
        "temporal_threshold_seconds": r.temporal_threshold_seconds,
        "conditions": r.conditions,
    }
