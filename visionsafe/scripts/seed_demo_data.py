"""
VisionSafe Demo Seed Script.

Populates SQLite database with realistic industrial safety data:
  - 4 Surveillance Cameras
  - 4 Safety Hazard Zones
  - 4 Operational Safety Rules
  - High-quality synthetic CCTV evidence frame images
  - 8 Realistic Safety Events across severities and statuses

Usage:
  python scripts/seed_demo_data.py
"""

import asyncio
import os
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path
import numpy as np
from PIL import Image, ImageDraw, ImageFont

# Add backend directory to sys.path
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR / "backend"))

from app.core.config import settings
from app.db.database import AsyncSessionLocal, engine, Base
from app.db.models import (
    Camera,
    Zone,
    Rule,
    SafetyEvent,
    EventEvidence,
    Severity,
    EventStatus,
    ZoneType,
)


def create_mock_evidence_image(
    file_path: Path,
    camera_name: str,
    event_title: str,
    worker_label: str,
    severity: str,
    box_color: tuple = (239, 68, 68),
):
    """Generate a realistic industrial CCTV annotated evidence frame."""
    width, height = 960, 540
    # Create dark industrial CCTV style background
    img = Image.new("RGB", (width, height), color=(26, 32, 44))
    draw = ImageDraw.Draw(img)

    # Grid / floor perspective lines
    for y in range(200, height, 40):
        draw.line([(0, y), (width, y)], fill=(38, 46, 61), width=1)
    for x in range(0, width, 80):
        draw.line([(x, 200), (x - 60, height)], fill=(33, 41, 54), width=1)

    # Draw hazard zone polygon on floor
    zone_pts = [(160, 240), (520, 240), (600, 480), (120, 480)]
    draw.polygon(zone_pts, fill=(239, 68, 68, 40), outline=(239, 68, 68), width=2)
    draw.text((180, 250), "[RESTRICTED FORKLIFT CORRIDOR]", fill=(239, 68, 68))

    # Draw worker bounding box
    wx1, wy1, wx2, wy2 = 320, 160, 440, 440
    draw.rectangle([wx1, wy1, wx2, wy2], outline=box_color, width=3)

    # Foot point (bottom-center contact)
    foot_x, foot_y = (wx1 + wx2) // 2, wy2
    draw.ellipse([foot_x - 6, foot_y - 6, foot_x + 6, foot_y + 6], fill=(59, 130, 246), outline=(255, 255, 255))
    draw.text((foot_x + 10, foot_y - 10), "Ground Contact Point", fill=(147, 197, 253))

    # Worker label badge
    draw.rectangle([wx1, wy1 - 24, wx1 + 140, wy1], fill=box_color)
    draw.text((wx1 + 6, wy1 - 20), worker_label, fill=(255, 255, 255))

    # PPE badges next to worker
    draw.rectangle([wx2 + 10, wy1, wx2 + 130, wy1 + 22], fill=(220, 38, 38))
    draw.text((wx2 + 16, wy1 + 4), "HELMET: NO", fill=(255, 255, 255))

    draw.rectangle([wx2 + 10, wy1 + 28, wx2 + 130, wy1 + 50], fill=(22, 163, 74))
    draw.text((wx2 + 16, wy1 + 32), "VEST: YES", fill=(255, 255, 255))

    # CCTV timestamp and telemetry overlay
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    draw.rectangle([0, 0, width, 40], fill=(15, 23, 42))
    draw.text((20, 12), f"VISIONSAFE AI — {camera_name.upper()} | {now_str} [LIVE STREAM]", fill=(203, 213, 225))

    # Alert banner at bottom
    banner_color = (185, 28, 28) if severity == "CRITICAL" else (194, 65, 12)
    draw.rectangle([0, height - 42, width, height], fill=banner_color)
    draw.text((20, height - 30), f"SAFETY ALERT: {event_title.upper()} — PERSISTENCE VERIFIED", fill=(255, 255, 255))

    file_path.parent.mkdir(parents=True, exist_ok=True)
    img.save(file_path, "JPEG", quality=85)


async def seed_data():
    print("Connecting to database and provisioning tables...")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    evidence_dir = BASE_DIR / "evidence"
    evidence_dir.mkdir(parents=True, exist_ok=True)

    async with AsyncSessionLocal() as session:
        # Check if already seeded
        from sqlalchemy import select, func
        cam_count = (await session.execute(select(func.count(Camera.id)))).scalar() or 0
        if cam_count > 0:
            print(f"Database already contains {cam_count} cameras. Clearing existing demo records for a clean slate...")
            await session.execute(SafetyEvent.__table__.delete())
            await session.execute(Zone.__table__.delete())
            await session.execute(Rule.__table__.delete())
            await session.execute(Camera.__table__.delete())
            await session.commit()

        print("Seeding Cameras...")
        cam1 = Camera(name="Camera 01 - Heavy Fabrication Bay", location="Building A, Sector 2", description="High bay overhead PTZ surveillance")
        cam2 = Camera(name="Camera 02 - Forklift Transit & Loading Dock", location="Warehouse East, Dock 4", description="Wide angle lane view")
        cam3 = Camera(name="Camera 03 - Chemical Storage Perimeter", location="Storage Yard B", description="Perimeter monitoring")
        cam4 = Camera(name="Camera 04 - Pedestrian Walkway Crossing", location="Main Concourse", description="Pedestrian crossing detection")
        session.add_all([cam1, cam2, cam3, cam4])
        await session.flush()

        print("Seeding Safety Zones...")
        zone_forklift = Zone(
            camera_id=cam2.id,
            name="Forklift High-Speed Lane",
            description="Active heavy machinery transit zone — pedestrians strictly prohibited",
            zone_type=ZoneType.RESTRICTED,
            severity=Severity.CRITICAL,
            polygon=[[120, 240], [520, 240], [600, 480], [120, 480]],
            required_ppe=[],
            color="#EF4444",
        )
        zone_ppe = Zone(
            camera_id=cam1.id,
            name="Assembly Floor PPE Zone",
            description="Hard hat and high-visibility vest mandatory at all times",
            zone_type=ZoneType.PPE_REQUIRED,
            severity=Severity.HIGH,
            polygon=[[80, 100], [880, 100], [880, 500], [80, 500]],
            required_ppe=["helmet", "vest"],
            color="#F59E0B",
        )
        zone_chem = Zone(
            camera_id=cam3.id,
            name="Hazardous Hazmat Perimeter",
            description="Exclusion zone around pressurized chemical tanks",
            zone_type=ZoneType.RESTRICTED,
            severity=Severity.CRITICAL,
            polygon=[[200, 150], [700, 150], [700, 450], [200, 450]],
            required_ppe=["helmet", "vest"],
            color="#8B5CF6",
        )
        zone_safe = Zone(
            camera_id=cam4.id,
            name="Green Safety Walkway",
            description="Designated safe path for foot traffic",
            zone_type=ZoneType.SAFE,
            severity=Severity.LOW,
            polygon=[[100, 300], [800, 300], [800, 420], [100, 420]],
            required_ppe=[],
            color="#10B981",
        )
        session.add_all([zone_forklift, zone_ppe, zone_chem, zone_safe])
        await session.flush()

        print("Seeding Safety Rules...")
        r_helmet = Rule(
            name="Mandatory Hard Hat Policy",
            description="Worker detected without an associated safety helmet",
            rule_type="NO_HELMET",
            severity=Severity.HIGH,
            temporal_threshold_seconds=1.5,
            conditions={"confidence_threshold": 0.5},
        )
        r_vest = Rule(
            name="High-Visibility Vest Requirement",
            description="Worker detected without an associated hi-vis vest in transit area",
            rule_type="NO_VEST",
            severity=Severity.MEDIUM,
            temporal_threshold_seconds=2.0,
            conditions={"confidence_threshold": 0.45},
        )
        r_zone = Rule(
            name="Restricted Zone Unauthorized Entry",
            description="Worker foot contact point detected inside restricted polygon",
            rule_type="RESTRICTED_ZONE_ENTRY",
            severity=Severity.CRITICAL,
            temporal_threshold_seconds=1.0,
            conditions={"check_foot_point": True},
        )
        r_prox = Rule(
            name="Forklift-Pedestrian Proximity Hazard",
            description="Worker within critical Euclidean distance threshold of moving forklift",
            rule_type="FORKLIFT_PROXIMITY",
            severity=Severity.CRITICAL,
            temporal_threshold_seconds=1.0,
            conditions={"max_distance_pixels": 140},
        )
        session.add_all([r_helmet, r_vest, r_zone, r_prox])
        await session.flush()

        print("Generating Realistic Evidence Images...")
        now = datetime.now(timezone.utc)
        
        img1_path = evidence_dir / "evidence_event_1.jpg"
        create_mock_evidence_image(
            img1_path,
            cam2.name,
            "Worker in Forklift Transit Path",
            "Worker #27",
            "CRITICAL",
            box_color=(239, 68, 68),
        )

        img2_path = evidence_dir / "evidence_event_2.jpg"
        create_mock_evidence_image(
            img2_path,
            cam1.name,
            "Missing Hard Hat in Assembly Bay",
            "Worker #14",
            "HIGH",
            box_color=(245, 158, 11),
        )

        img3_path = evidence_dir / "evidence_event_3.jpg"
        create_mock_evidence_image(
            img3_path,
            cam3.name,
            "Unauthorized Entry into Hazmat Yard",
            "Worker #09",
            "CRITICAL",
            box_color=(139, 92, 246),
        )

        img4_path = evidence_dir / "evidence_event_4.jpg"
        create_mock_evidence_image(
            img4_path,
            cam1.name,
            "Missing High-Visibility Vest",
            "Worker #31",
            "MEDIUM",
            box_color=(59, 130, 246),
        )

        print("Seeding Safety Events...")
        events = [
            SafetyEvent(
                camera_id=cam2.id,
                rule_id=r_zone.id,
                zone_id=zone_forklift.id,
                event_type="RESTRICTED_ZONE_ENTRY",
                severity=Severity.CRITICAL,
                status=EventStatus.OPEN,
                subject_track_id=27,
                related_track_id=4,  # Forklift #4
                started_at=now - timedelta(minutes=14, seconds=4),
                detected_at=now - timedelta(minutes=14),
                duration_seconds=4.2,
                confidence=0.94,
                description="Worker #27 crossed into restricted Forklift High-Speed Lane while Forklift #4 was active.",
                evidence_frame_path="/evidence/evidence_event_1.jpg",
                event_metadata={"distance_to_machinery_px": 88, "zone_name": "Forklift High-Speed Lane"},
            ),
            SafetyEvent(
                camera_id=cam1.id,
                rule_id=r_helmet.id,
                zone_id=zone_ppe.id,
                event_type="NO_HELMET",
                severity=Severity.HIGH,
                status=EventStatus.OPEN,
                subject_track_id=14,
                started_at=now - timedelta(minutes=32, seconds=8),
                detected_at=now - timedelta(minutes=32),
                duration_seconds=8.5,
                confidence=0.91,
                description="Worker #14 detected without safety helmet in mandatory overhead crane fabrication zone.",
                evidence_frame_path="/evidence/evidence_event_2.jpg",
                event_metadata={"missing_item": "helmet", "vest_detected": True},
            ),
            SafetyEvent(
                camera_id=cam3.id,
                rule_id=r_zone.id,
                zone_id=zone_chem.id,
                event_type="RESTRICTED_ZONE_ENTRY",
                severity=Severity.CRITICAL,
                status=EventStatus.ACKNOWLEDGED,
                subject_track_id=9,
                started_at=now - timedelta(hours=1, minutes=15),
                detected_at=now - timedelta(hours=1, minutes=15),
                duration_seconds=3.1,
                confidence=0.89,
                description="Worker #09 breached hazardous perimeter fence without authorization badge.",
                evidence_frame_path="/evidence/evidence_event_3.jpg",
                event_metadata={"zone": "Hazardous Hazmat Perimeter"},
            ),
            SafetyEvent(
                camera_id=cam1.id,
                rule_id=r_vest.id,
                zone_id=zone_ppe.id,
                event_type="NO_VEST",
                severity=Severity.MEDIUM,
                status=EventStatus.RESOLVED,
                subject_track_id=31,
                started_at=now - timedelta(hours=2, minutes=45),
                detected_at=now - timedelta(hours=2, minutes=45),
                ended_at=now - timedelta(hours=2, minutes=40),
                duration_seconds=300.0,
                confidence=0.87,
                description="Worker #31 vest missing during morning shift handover. Worker retrieved PPE upon supervisor alert.",
                evidence_frame_path="/evidence/evidence_event_4.jpg",
                event_metadata={"resolution_notes": "Supervisor issued replacement vest"},
            ),
            SafetyEvent(
                camera_id=cam2.id,
                rule_id=r_prox.id,
                zone_id=zone_forklift.id,
                event_type="FORKLIFT_PROXIMITY",
                severity=Severity.CRITICAL,
                status=EventStatus.RESOLVED,
                subject_track_id=18,
                related_track_id=2,
                started_at=now - timedelta(hours=4, minutes=10),
                detected_at=now - timedelta(hours=4, minutes=10),
                ended_at=now - timedelta(hours=4, minutes=8),
                duration_seconds=120.0,
                confidence=0.96,
                description="Critical near-miss proximity alert: Worker #18 was within 1.1 meters of reversing Forklift #2.",
                evidence_frame_path="/evidence/evidence_event_1.jpg",
                event_metadata={"min_distance_m": 1.1, "operator_alerted": True},
            ),
            SafetyEvent(
                camera_id=cam1.id,
                rule_id=r_helmet.id,
                zone_id=zone_ppe.id,
                event_type="NO_HELMET",
                severity=Severity.HIGH,
                status=EventStatus.RESOLVED,
                subject_track_id=22,
                started_at=now - timedelta(hours=6, minutes=20),
                detected_at=now - timedelta(hours=6, minutes=20),
                ended_at=now - timedelta(hours=6, minutes=18),
                duration_seconds=120.0,
                confidence=0.88,
                description="Worker #22 took off helmet while operating drill press.",
                evidence_frame_path="/evidence/evidence_event_2.jpg",
                event_metadata={},
            ),
            SafetyEvent(
                camera_id=cam4.id,
                rule_id=r_vest.id,
                zone_id=zone_safe.id,
                event_type="NO_VEST",
                severity=Severity.LOW,
                status=EventStatus.FALSE_POSITIVE,
                subject_track_id=45,
                started_at=now - timedelta(hours=8, minutes=5),
                detected_at=now - timedelta(hours=8, minutes=5),
                duration_seconds=2.0,
                confidence=0.62,
                description="Worker carrying large cardboard box temporarily occluded high-visibility vest.",
                evidence_frame_path="/evidence/evidence_event_4.jpg",
                event_metadata={"marked_by": "Safety Officer", "reason": "Severe occlusion"},
            ),
        ]
        session.add_all(events)
        await session.commit()

    print("\n[OK] Successfully seeded demo data!")
    print(f"  - 4 Cameras")
    print(f"  - 4 Safety Zones")
    print(f"  - 4 Safety Rules")
    print(f"  - 7 Safety Events (Open, Acknowledged, Resolved, False Positive)")
    print(f"  - 4 Annotated Evidence Frames saved in {evidence_dir}")
    print("\nRefresh your browser at http://localhost:5173 to view the live dashboard!")


if __name__ == "__main__":
    asyncio.run(seed_data())
