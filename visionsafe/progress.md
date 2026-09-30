# VisionSafe — Build Progress Tracker

> Last updated: 2026-09-29 by Phase 1–2 build agent.
> Next model: pick up from Phase 3.

---

## ✅ Phase 1 — Repository (COMPLETE)

### Files Created

**Root:**
- `.env.example` — all environment variables documented
- `.gitignore` — Python, Node, models, videos, evidence
- `pyproject.toml` — build system + pytest + ruff + mypy config
- `requirements.txt` — pinned Python dependencies
- `docker-compose.yml` — postgres + backend + frontend services
- `README.md` — full architecture + quick-start documentation

**Backend:**
- `backend/app/main.py` — FastAPI application factory with lifespan, CORS, routers
- `backend/app/core/config.py` — Pydantic-settings configuration from env
- `backend/app/core/logging.py` — structured logging + `get_logger()`
- `backend/app/db/database.py` — async SQLAlchemy engine, session factory, `get_db` dependency
- `backend/app/db/models/models.py` — ORM models: Camera, Video, ProcessingJob, Zone, Rule, SafetyEvent, EventEvidence
- `backend/app/api/routes/cameras.py` — Camera CRUD
- `backend/app/api/routes/videos.py` — video upload + background processing job
- `backend/app/api/routes/zones.py` — Zone CRUD with polygon validation
- `backend/app/api/routes/rules.py` — Rule CRUD
- `backend/app/api/routes/events.py` — Events with filtering + PATCH for acknowledge/resolve
- `backend/app/api/routes/analytics.py` — summary + violations-by-type
- `backend/app/api/routes/workers.py` — stub (track IDs only, no biometrics)
- `backend/alembic/env.py` — async Alembic migration env
- `backend/alembic.ini` — Alembic config
- `backend/tests/test_vision.py` — unit tests (30+ assertions, no GPU required)

**Vision layer (Phase 2):**
- `backend/app/vision/detections.py` — Detection, TrackedObject (with foot position), PPEState, FrameResult dataclasses
- `backend/app/vision/detector.py` — ObjectDetector ABC + YOLODetector (Ultralytics, CUDA fallback)
- `backend/app/vision/tracker.py` — ObjectTracker (BoT-SORT via Ultralytics model.track())
- `backend/app/vision/association.py` — PPE geometric association engine (helmet upper-region, vest torso-region)
- `backend/app/vision/coordinates.py` — CoordinateTransformer ABC, ImageCoordinateTransformer (V1), HomographyCoordinateTransformer (stub)
- `backend/app/vision/video_source.py` — VideoSource ABC, FileVideoSource
- `backend/app/vision/annotator.py` — frame annotation: bboxes, PPE status, zones, metrics, evidence frames
- `backend/app/vision/pipeline.py` — InferencePipeline + AnnotatedVideoWriter

**ML:**
- `ml/inference.py` — Phase 2 CLI: `video → YOLO → annotated output MP4`
- `ml/train.py` — YOLO training script (RTX 3050 tuned)
- `ml/evaluate.py` — model evaluation (mAP50, precision, recall)
- `ml/configs/construction.yaml` — dataset config (4 classes: person, helmet, vest, forklift)

**Docker:**
- `docker/Dockerfile.backend`
- `docker/Dockerfile.frontend`

**Frontend (React + Vite + TypeScript + Tailwind):**
- `frontend/src/App.tsx` — React Router with 6 pages
- `frontend/src/index.css` — Tailwind + custom dark theme tokens
- `frontend/tailwind.config.js` — brand palette + severity colors + animations
- `frontend/postcss.config.js`
- `frontend/src/components/layout/Layout.tsx` — sidebar + main content
- `frontend/src/services/api.ts` — typed API client for all endpoints
- `frontend/src/pages/DashboardPage.tsx` — stats + charts + recent events
- `frontend/src/pages/EventsPage.tsx` — filterable event table + detail modal
- `frontend/src/pages/VideosPage.tsx` — upload + processing + progress bar
- `frontend/src/pages/ZonesPage.tsx` — zone create + list with color/polygon/PPE
- `frontend/src/pages/RulesPage.tsx` — rule create + toggle enable/disable
- `frontend/src/pages/AnalyticsPage.tsx` — bar + pie charts from real DB data

---

## ✅ Phase 2 — YOLO Inference (COMPLETE)

The pipeline is fully implemented and testable without a database:

```bash
python ml/inference.py --input videos/sample.mp4 --device cpu
# Produces: videos/sample_annotated.mp4
# Shows: Worker #N labels, PPE status (H✓/H✗ V✓/V✗), foot-point dots, FPS overlay
```

**What works:**
1. FileVideoSource reads any MP4
2. YOLODetector runs YOLO on each frame (auto-downloads yolov8n.pt)
3. ObjectTracker (BoT-SORT) assigns stable Worker #N and Forklift #N IDs
4. PPE association engine links helmets/vests to workers geometrically
5. AnnotatedVideoWriter writes output MP4

**Tests passing:**
```
pytest backend/tests/ -v
# 20+ tests, 0 failures, no GPU required
```

---

## 🔜 Phase 3 — Tracking Integration + Zone Engine

**What to implement next:**

### 3a. Zone point-in-polygon engine
File: `backend/app/safety/zone_engine.py`

```python
class ZoneEngine:
    def point_in_polygon(self, point: tuple, polygon: list) -> bool:
        # Ray-casting algorithm
        ...

    def check_workers_in_zones(self, persons: list[TrackedObject], zones: list[Zone]) -> dict:
        # Returns {track_id: [zone_ids]}
        ...
```

- Use the **foot point** (TrackedObject.foot_x, foot_y) for zone membership
- Implement ENTERED / REMAINING / EXITED state machine per worker per zone
- Tests: write test_zone_engine.py covering entry, exit, polygon edges

### 3b. Zone state machine
```python
class ZoneStateMachine:
    """Track ENTERED/REMAINING/EXITED transitions per (track_id, zone_id)."""
    
    def update(self, track_id: int, zone_id: int, inside: bool) -> ZoneEvent | None:
        ...
```

### 3c. Temporal violation engine
File: `backend/app/safety/temporal_engine.py`

```python
class TemporalEngine:
    """
    Accumulates violation evidence over multiple frames.
    Only creates a safety event after the persistence threshold is met.
    
    Key: (track_id, rule_type, zone_id)
    Value: ViolationState(started_at, frame_count, threshold)
    """
```

Tests required (per spec):
- Person in zone 0.5s → no event
- Person in zone 2.5s → event created
- Person exits → event closed, ended_at set

### 3d. PPE engine
File: `backend/app/safety/ppe_engine.py`

Evaluate PPE compliance rules per zone configuration.

---

## 🔜 Phase 4 — Safety Rule Engine

File: `backend/app/safety/rule_engine.py`

Rules to implement:
- `NO_HELMET` — person detected, no helmet associated
- `NO_VEST` — person detected, no vest associated
- `RESTRICTED_ZONE_ENTRY` — person foot in restricted zone
- `FORKLIFT_PROXIMITY` — Euclidean pixel distance below threshold
- `RESTRICTED_ZONE_PPE` — person in zone without required PPE

Each rule must output:
```python
RuleViolation(
    rule_id, event_type, severity,
    subject_track_id, related_track_id,
    zone_id, confidence, description
)
```

---

## 🔜 Phase 5 — Zone Drawing UI

Frontend: Add canvas polygon drawing to ZonesPage.
The user should be able to:
1. Load a video frame as background
2. Click to place polygon vertices
3. Double-click to close polygon
4. Submit zone with drawn polygon

---

## 🔜 Phase 6–14 — Remaining Phases

- Phase 6: Integrate safety engine into pipeline
- Phase 7: Persist events to PostgreSQL in background job
- Phase 8: WebSocket real-time event streaming
- Phase 9: Evidence frame saving
- Phase 10: Proximity engine + distance display
- Phase 11: Analytics from real events
- Phase 12: Full Docker with GPU support
- Phase 13: Forklift dynamic danger zones (design only)
- Phase 14: End-to-end demo scenario

---

## Architecture Decisions Made

| Decision | Rationale |
|----------|-----------|
| YOLO ≠ safety decisions | Spec requirement — keeps safety auditable |
| Foot point for zones | Bottom-center approximates ground contact |
| BoT-SORT over ByteTrack | Better re-identification with occlusion |
| Pixel distances (V1) | Clear abstraction for future homography |
| Temporal persistence | No single-frame events (reduces false positives) |
| FileVideoSource first | Simpler than RTSP for MVP verification |
| yolov8n.pt default | RTX 3050 4GB safe, ~15-20 FPS |

---

## Current Limitations

1. Safety engine not yet connected to pipeline (Phase 3)
2. No real-time WebSocket events yet (Phase 8)
3. Zone drawing is text-based JSON (Phase 5 will add canvas)
4. Database not yet populated by video processing (Phase 7)
5. Evidence frames not yet saved automatically (Phase 9)
6. RTSP/live camera not yet supported (by design, Phase 14+)
7. No authentication implemented (Phase 3+)

---

## Commands Quick Reference

```bash
# Activate venv (Windows)
.venv\Scripts\activate

# Run tests (no GPU/DB required)
pytest backend/tests/ -v

# Run inference CLI (Phase 2)
python ml/inference.py --input videos/sample.mp4 --device cpu

# Run backend
cd backend && uvicorn app.main:app --reload

# Run frontend
cd frontend && npm run dev

# Start all via Docker
docker compose up

# Train model (after dataset prep)
python ml/train.py --data ml/configs/construction.yaml --model yolov8n.pt --device 0
```
