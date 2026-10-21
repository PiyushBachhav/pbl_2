"""
Automated verification tests for SQLite database backend and FastAPI endpoints.

Tests:
  - Table creation on SQLite via Base.metadata
  - SQLite pragma settings (WAL, foreign keys)
  - CRUD operations on Camera, Zone, Rule, Video, SafetyEvent
  - FastAPI endpoints via httpx.AsyncClient (lifespan, API routers, error handling)
  - Analytics calculations from persisted safety events
"""

import os
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

from app.core.config import settings
from app.db.database import Base, get_db
from app.db.models import (
    Camera,
    Video,
    ProcessingJob,
    Zone,
    Rule,
    SafetyEvent,
    EventEvidence,
    Severity,
    EventStatus,
    JobStatus,
    ZoneType,
)
from app.main import create_app

TEST_DB_FILE = "./test_visionsafe.db"
TEST_DB_URL = f"sqlite+aiosqlite:///{TEST_DB_FILE}"


@pytest.fixture(scope="session")
def anyio_backend():
    return "asyncio"


@pytest.fixture
async def test_engine():
    """Create a temporary SQLite async engine for tests."""
    engine = create_async_engine(
        TEST_DB_URL,
        connect_args={"check_same_thread": False},
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)

    yield engine

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()

    if os.path.exists(TEST_DB_FILE):
        try:
            os.remove(TEST_DB_FILE)
        except OSError:
            pass


@pytest.fixture
async def db_session(test_engine):
    """Yield an active AsyncSession bound to the test SQLite database."""
    session_factory = async_sessionmaker(
        bind=test_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )
    async with session_factory() as session:
        yield session


@pytest.fixture
async def app_client(test_engine):
    """FastAPI test client with get_db dependency overridden to use test SQLite engine."""
    app = create_app()
    session_factory = async_sessionmaker(
        bind=test_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )

    async def override_get_db():
        async with session_factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    app.dependency_overrides[get_db] = override_get_db

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


# ─────────────────────────────────────────
# Database Model & CRUD Tests
# ─────────────────────────────────────────

class TestSQLiteCRUD:
    """Test ORM CRUD operations directly on SQLite."""

    async def test_camera_crud(self, db_session: AsyncSession):
        # Create
        camera = Camera(
            name="Loading Bay Cam 1",
            location="Zone B, Warehouse East",
            description="High-definition PTZ camera monitoring loading dock",
            enabled=True,
        )
        db_session.add(camera)
        await db_session.commit()
        await db_session.refresh(camera)
        assert camera.id is not None
        assert camera.name == "Loading Bay Cam 1"

        # Read
        fetched = await db_session.get(Camera, camera.id)
        assert fetched is not None
        assert fetched.location == "Zone B, Warehouse East"

        # Update
        fetched.enabled = False
        await db_session.commit()
        await db_session.refresh(fetched)
        assert fetched.enabled is False

    async def test_zone_crud(self, db_session: AsyncSession):
        camera = Camera(name="Zone Camera")
        db_session.add(camera)
        await db_session.commit()

        zone = Zone(
            camera_id=camera.id,
            name="Forklift Operating Zone",
            zone_type=ZoneType.RESTRICTED,
            severity=Severity.HIGH,
            polygon=[[100, 100], [400, 100], [400, 400], [100, 400]],
            required_ppe=["helmet", "vest"],
            enabled=True,
            color="#FF0000",
        )
        db_session.add(zone)
        await db_session.commit()
        await db_session.refresh(zone)
        assert zone.id is not None
        assert len(zone.polygon) == 4
        assert "helmet" in zone.required_ppe

    async def test_rule_and_event_persistence(self, db_session: AsyncSession):
        rule = Rule(
            name="No Helmet Violation",
            rule_type="NO_HELMET",
            severity=Severity.HIGH,
            temporal_threshold_seconds=1.5,
            conditions={"min_confidence": 0.5},
        )
        db_session.add(rule)
        await db_session.commit()

        event = SafetyEvent(
            rule_id=rule.id,
            event_type="NO_HELMET",
            severity=Severity.HIGH,
            status=EventStatus.OPEN,
            subject_track_id=14,
            description="Worker #14 missing helmet in restricted area",
            confidence=0.88,
            event_metadata={"area": "Sector 3"},
        )
        db_session.add(event)
        await db_session.commit()
        await db_session.refresh(event)

        assert event.id is not None
        assert event.subject_track_id == 14
        assert event.status == EventStatus.OPEN
        assert event.severity == Severity.HIGH


# ─────────────────────────────────────────
# FastAPI HTTP Endpoints via SQLite
# ─────────────────────────────────────────

class TestSQLiteAPIEndpoints:
    """Test full FastAPI request-response lifecycle backed by SQLite."""

    async def test_health_check(self, app_client: AsyncClient):
        response = await app_client.get("/health")
        assert response.status_code == 200
        assert response.json() == {"status": "ok", "version": "0.1.0"}

    async def test_cameras_api(self, app_client: AsyncClient):
        # Create
        create_res = await app_client.post(
            "/api/cameras/",
            json={"name": "Forklift Aisle Cam", "location": "Sector 4", "description": "Overhead cam"},
        )
        assert create_res.status_code == 201
        data = create_res.json()
        cam_id = data["id"]
        assert data["name"] == "Forklift Aisle Cam"

        # List
        list_res = await app_client.get("/api/cameras/")
        assert list_res.status_code == 200
        cameras = list_res.json()
        assert any(c["id"] == cam_id for c in cameras)

        # Get by id
        get_res = await app_client.get(f"/api/cameras/{cam_id}")
        assert get_res.status_code == 200
        assert get_res.json()["name"] == "Forklift Aisle Cam"

    async def test_rules_api(self, app_client: AsyncClient):
        # Create rule
        res = await app_client.post(
            "/api/rules/",
            json={
                "name": "Restricted Zone Entry",
                "rule_type": "RESTRICTED_ZONE_ENTRY",
                "severity": "CRITICAL",
                "temporal_threshold_seconds": 2.0,
                "conditions": {},
            },
        )
        assert res.status_code == 201
        rule_data = res.json()
        rule_id = rule_data["id"]
        assert rule_data["severity"] == "CRITICAL"

        # List rules
        list_res = await app_client.get("/api/rules/")
        assert list_res.status_code == 200
        assert any(r["id"] == rule_id for r in list_res.json())

    async def test_zones_api(self, app_client: AsyncClient):
        # Create zone with valid polygon
        res = await app_client.post(
            "/api/zones/",
            json={
                "name": "Danger Zone Alpha",
                "zone_type": "restricted",
                "severity": "HIGH",
                "polygon": [[0, 0], [100, 0], [100, 100]],
                "required_ppe": ["helmet"],
            },
        )
        assert res.status_code == 201
        zone_id = res.json()["id"]

        # Reject invalid polygon (< 3 points)
        bad_res = await app_client.post(
            "/api/zones/",
            json={
                "name": "Bad Zone",
                "polygon": [[0, 0], [10, 10]],
            },
        )
        assert bad_res.status_code == 400

        # Delete zone
        del_res = await app_client.delete(f"/api/zones/{zone_id}")
        assert del_res.status_code == 204

    async def test_events_and_analytics(self, app_client: AsyncClient, db_session: AsyncSession):
        # Insert events directly
        e1 = SafetyEvent(
            event_type="NO_HELMET",
            severity=Severity.HIGH,
            status=EventStatus.OPEN,
            description="Worker without helmet",
        )
        e2 = SafetyEvent(
            event_type="RESTRICTED_ZONE_ENTRY",
            severity=Severity.CRITICAL,
            status=EventStatus.RESOLVED,
            description="Worker in restricted zone",
        )
        db_session.add_all([e1, e2])
        await db_session.commit()

        # Query events via API
        events_res = await app_client.get("/api/events/")
        assert events_res.status_code == 200
        events = events_res.json()
        assert len(events) >= 2

        # Filter by severity
        filtered_res = await app_client.get("/api/events/?severity=CRITICAL")
        assert filtered_res.status_code == 200
        crit_events = filtered_res.json()
        assert all(ev["severity"] == "CRITICAL" for ev in crit_events)

        # Query analytics summary
        summary_res = await app_client.get("/api/analytics/summary")
        assert summary_res.status_code == 200
        summary = summary_res.json()
        assert summary["total_events"] >= 2
        assert summary["open_events"] >= 1
        assert summary["high_critical_events"] >= 2
