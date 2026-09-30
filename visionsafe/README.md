# VisionSafe — Industrial Safety Intelligence Platform

> **Experimental portfolio project.** This is NOT a certified workplace safety system.
> Do not rely on it for actual safety-critical decisions.

---

## Architecture Overview

```
Video
  ↓  FileVideoSource
Frame extraction
  ↓  YOLODetector
YOLO detection (person / helmet / vest / forklift)
  ↓  ObjectTracker (BoT-SORT)
Persistent tracking IDs
  ↓  association.build_ppe_states()
PPE association (geometric bbox analysis)
  ↓  FrameResult
Safety rule engine  ← Phase 3+
  ↓
Temporal validation  ← Phase 6+
  ↓
Safety event → PostgreSQL → WebSocket → Dashboard
```

**Critical principle:** YOLO detects objects. The safety engine determines violations.
These are separate components that never call each other directly.

---

## Project Structure

```
visionsafe/
├── backend/
│   ├── app/
│   │   ├── main.py           # FastAPI application factory
│   │   ├── core/             # Config + logging
│   │   ├── db/               # SQLAlchemy models + database
│   │   ├── api/routes/       # REST API endpoints
│   │   ├── vision/           # CV pipeline (detector, tracker, association)
│   │   ├── safety/           # Safety rules engine (Phase 3+)
│   │   └── websocket/        # Real-time event streaming (Phase 11+)
│   └── tests/
│       └── test_vision.py    # Unit tests for CV + association logic
│
├── frontend/                 # React + TypeScript + Vite + Tailwind
│   └── src/
│       ├── pages/            # Dashboard, Events, Videos, Zones, Rules, Analytics
│       ├── services/api.ts   # Typed API client
│       └── components/       # Reusable UI components
│
├── ml/
│   ├── inference.py          # Phase 2 CLI: video → YOLO → annotated output
│   ├── train.py              # YOLO training script
│   ├── evaluate.py           # Model evaluation
│   └── configs/construction.yaml  # Dataset config (4 classes)
│
├── models/                   # YOLO .pt files (not committed)
├── videos/                   # Input videos (not committed)
├── evidence/                 # Saved event frames
├── docker-compose.yml
└── .env.example
```

---

## V1 Object Classes

```yaml
0: person
1: helmet
2: vest
3: forklift
```

Additional classes are architecturally supported — add to `CLASS_MAP` in
`backend/app/vision/detector.py` and retrain.

---

## Quick Start (Local, No Docker)

### 1. Clone and create environment

```bash
git clone <repo>
cd visionsafe

python -m venv .venv
# Windows:
.venv\Scripts\activate
# Linux/Mac:
source .venv/bin/activate

pip install -r requirements.txt
```

### 2. Configure environment

```bash
cp .env.example .env
# Edit .env — set DATABASE_URL, DEVICE, MODEL_PATH
```

### 3. Start PostgreSQL

```bash
# Docker (easiest):
docker run -d --name visionsafe_db \
  -e POSTGRES_USER=visionsafe \
  -e POSTGRES_PASSWORD=visionsafe \
  -e POSTGRES_DB=visionsafe \
  -p 5432:5432 postgres:16-alpine
```

### 4. Run backend

```bash
cd backend
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
# API docs: http://localhost:8000/api/docs
```

### 5. Run frontend

```bash
cd frontend
npm install
npm run dev
# Dashboard: http://localhost:5173
```

---

## Phase 2: YOLO Inference CLI

Run detection + tracking on a video file:

```bash
# CPU (development)
python ml/inference.py --input videos/sample.mp4 --device cpu

# CUDA (RTX 3050)
python ml/inference.py --input videos/sample.mp4 --device cuda

# Options
python ml/inference.py \
  --input videos/sample.mp4 \
  --output videos/sample_annotated.mp4 \
  --model yolov8n.pt \
  --device cuda \
  --confidence 0.35 \
  --skip 1

# Output: videos/sample_annotated.mp4 with bounding boxes and PPE status
```

The default model (`yolov8n.pt`) auto-downloads from Ultralytics on first run.

---

## Run Tests

```bash
# From visionsafe/ directory with venv activated
pytest backend/tests/ -v

# Expected output:
# PASSED tests/test_vision.py::TestFootPosition::test_foot_position_centered
# PASSED tests/test_vision.py::TestHelmetAssociation::test_helmet_in_upper_region
# ... (20+ tests)
```

Tests cover:
- Foot position calculation
- Coordinate transformer
- IoU computation
- Helmet/vest geometric association
- PPE state building for multiple workers

Tests do **not** require a GPU, database, or trained model.

---

## Model Training

### 1. Prepare dataset

```
ml/datasets/construction_ppe/
  images/train/
  images/val/
  images/test/
  labels/train/   # YOLO format
  labels/val/
  labels/test/
```

Recommended public datasets:
- [Safety Helmet Detection](https://www.kaggle.com/datasets/vodan37/safety-helmet-detection)
- [Construction Site Safety](https://universe.roboflow.com/roboflow-100/construction-site-safety)

### 2. Train

```bash
# RTX 3050 4GB — recommended settings
python ml/train.py \
  --data ml/configs/construction.yaml \
  --model yolov8n.pt \
  --epochs 50 \
  --imgsz 640 \
  --batch 16 \
  --device 0

# Copy best weights
cp runs/detect/<run_name>/weights/best.pt models/best.pt
```

### 3. Evaluate

```bash
python ml/evaluate.py \
  --model models/best.pt \
  --data ml/configs/construction.yaml \
  --device 0
```

Reports: Precision, Recall, mAP50, mAP50-95, per-class metrics.

---

## Docker

```bash
# Start all services
docker compose up

# Services:
#   postgres   → localhost:5432
#   backend    → http://localhost:8000
#   frontend   → http://localhost:5173
```

**GPU in Docker:** Install [NVIDIA Container Toolkit](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/install-guide.html)
and add `deploy.resources.reservations.devices` to the backend service.

---

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | /health | Health check |
| GET/POST | /api/cameras | Camera management |
| GET/POST | /api/videos | Video upload |
| POST | /api/videos/{id}/process | Start analysis |
| GET/POST/PUT/DELETE | /api/zones | Zone management |
| GET/POST/PUT | /api/rules | Rule management |
| GET | /api/events | Safety events (filterable) |
| PATCH | /api/events/{id} | Acknowledge / resolve |
| GET | /api/analytics/summary | Dashboard stats |
| GET | /api/analytics/violations | Violations by type |

Interactive docs: `http://localhost:8000/api/docs`

---

## Safety Disclaimer

This system is an experimental computer-vision portfolio project.

- It does NOT claim to meet OSHA, ISO, or any workplace safety standard
- Proximity thresholds are in **image-space pixels**, NOT real-world meters
- A safety officer should always review flagged events
- Do not use for certified safety compliance

---

## Phase Status

| Phase | Status | Description |
|-------|--------|-------------|
| 1 | ✅ Complete | Repository structure, FastAPI, React, Docker |
| 2 | ✅ Complete | YOLO inference + BoT-SORT tracking + PPE association CLI |
| 3 | 🔜 Next | Tracking persistence + zone point-in-polygon |
| 4 | 🔜 | PPE engine integration |
| 5 | 🔜 | Zone management UI with canvas drawing |
| 6 | 🔜 | Temporal violation persistence |
| 7 | 🔜 | Safety rule engine |
| 8 | 🔜 | Database persistence for events |
| 9 | 🔜 | Full REST API integration |
| 10 | 🔜 | WebSocket real-time dashboard |
| 11 | 🔜 | Evidence frame generation |
| 12 | 🔜 | Analytics from real data |
| 13 | 🔜 | Docker production setup |
