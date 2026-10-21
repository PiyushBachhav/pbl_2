"""
VisionSafe Backend — FastAPI application entry point.

Architecture overview:
  vision layer   → detects objects (YOLO + tracker)
  safety layer   → evaluates rules against detections
  api layer      → exposes results via REST + WebSocket
  db layer       → persists events, zones, rules

YOLO never decides what is dangerous; the safety engine does.
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.core.config import settings
from app.core.logging import configure_logging
from app.db.database import engine, Base
from app.db import models  # Ensures all ORM models are registered with Base.metadata
from app.api.routes import cameras, videos, zones, rules, events, analytics, workers


configure_logging()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Create DB tables on startup (Alembic handles migrations in production)."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    await engine.dispose()


def create_app() -> FastAPI:
    app = FastAPI(
        title="VisionSafe API",
        description=(
            "Industrial Safety Intelligence Platform. "
            "Detects safety violations in video streams using configurable rules."
        ),
        version="0.1.0",
        lifespan=lifespan,
        docs_url="/api/docs",
        redoc_url="/api/redoc",
        openapi_url="/api/openapi.json",
    )

    # --- CORS ---
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[settings.FRONTEND_URL, "http://localhost:5173"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # --- Routers ---
    prefix = "/api"
    app.include_router(cameras.router, prefix=prefix)
    app.include_router(videos.router, prefix=prefix)
    app.include_router(zones.router, prefix=prefix)
    app.include_router(rules.router, prefix=prefix)
    app.include_router(events.router, prefix=prefix)
    app.include_router(analytics.router, prefix=prefix)
    app.include_router(workers.router, prefix=prefix)

    # --- WebSocket real-time event streaming ---
    from app.websocket import ws_router
    app.include_router(ws_router, prefix=prefix)
    app.include_router(ws_router)

    # --- Static evidence frames & videos ---
    import os
    os.makedirs(settings.EVIDENCE_DIR, exist_ok=True)
    os.makedirs(settings.VIDEO_DIR, exist_ok=True)
    app.mount("/evidence", StaticFiles(directory=settings.EVIDENCE_DIR), name="evidence")
    app.mount("/videos", StaticFiles(directory=settings.VIDEO_DIR), name="videos")

    @app.get("/health", tags=["health"])
    async def health() -> dict:
        return {"status": "ok", "version": "0.1.0"}

    return app


app = create_app()
