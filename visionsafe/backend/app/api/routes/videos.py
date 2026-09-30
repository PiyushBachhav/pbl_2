"""
Video upload and processing API routes.

POST /videos            — upload video file
GET  /videos            — list videos
GET  /videos/{id}       — get video details + job status
POST /videos/{id}/process — start processing job
"""

from __future__ import annotations

import asyncio
import logging
import shutil
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.config import settings
from app.db.database import get_db
from app.db.models import Video, ProcessingJob, JobStatus

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/videos", tags=["videos"])

ALLOWED_EXTENSIONS = {".mp4", ".avi", ".mkv", ".mov", ".webm"}


@router.get("/", response_model=list[dict])
async def list_videos(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Video))
    videos = result.scalars().all()
    return [
        {
            "id": v.id,
            "filename": v.original_filename,
            "fps": v.fps,
            "duration_seconds": v.duration_seconds,
            "width": v.width,
            "height": v.height,
            "total_frames": v.total_frames,
        }
        for v in videos
    ]


@router.post("/", response_model=dict, status_code=201)
async def upload_video(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
):
    """Upload a video file for processing."""
    suffix = Path(file.filename).suffix.lower()
    if suffix not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported format '{suffix}'. Allowed: {ALLOWED_EXTENSIONS}",
        )

    # Save file
    unique_name = f"{uuid.uuid4().hex}{suffix}"
    dest = settings.video_path / unique_name
    with dest.open("wb") as f:
        shutil.copyfileobj(file.file, f)

    file_size = dest.stat().st_size

    # Extract basic video metadata via OpenCV
    fps, width, height, total_frames, duration = _probe_video(str(dest))

    video = Video(
        filename=unique_name,
        original_filename=file.filename,
        file_path=str(dest),
        file_size_bytes=file_size,
        fps=fps,
        width=width,
        height=height,
        total_frames=total_frames,
        duration_seconds=duration,
    )
    db.add(video)
    await db.flush()
    await db.refresh(video)

    logger.info(
        "Video uploaded | id=%d file=%s size=%d fps=%.1f",
        video.id, file.filename, file_size, fps or 0,
    )

    return {"id": video.id, "filename": file.filename, "duration_seconds": duration}


@router.get("/{video_id}", response_model=dict)
async def get_video(video_id: int, db: AsyncSession = Depends(get_db)):
    video = await db.get(Video, video_id)
    if not video:
        raise HTTPException(status_code=404, detail="Video not found")

    job = video.job
    return {
        "id": video.id,
        "filename": video.original_filename,
        "fps": video.fps,
        "duration_seconds": video.duration_seconds,
        "width": video.width,
        "height": video.height,
        "total_frames": video.total_frames,
        "job": {
            "status": job.status.value if job else None,
            "progress": job.progress if job else None,
            "fps_achieved": job.fps_achieved if job else None,
            "error": job.error_message if job else None,
        } if job else None,
    }


@router.post("/{video_id}/process", response_model=dict, status_code=202)
async def start_processing(
    video_id: int,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
):
    """Start background processing job for a video."""
    video = await db.get(Video, video_id)
    if not video:
        raise HTTPException(status_code=404, detail="Video not found")

    # Check existing job
    if video.job and video.job.status == JobStatus.RUNNING:
        raise HTTPException(status_code=409, detail="Processing already running")

    job = ProcessingJob(video_id=video.id, status=JobStatus.PENDING)
    db.add(job)
    await db.flush()
    await db.refresh(job)

    job_id = job.id
    video_path = video.file_path

    background_tasks.add_task(_run_processing_job, job_id, video_path)

    logger.info("Processing job %d queued for video %d", job_id, video_id)
    return {"job_id": job_id, "status": "PENDING", "message": "Processing started"}


# ─────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────

def _probe_video(path: str) -> tuple:
    """Extract video metadata using OpenCV."""
    try:
        import cv2
        cap = cv2.VideoCapture(path)
        fps = cap.get(cv2.CAP_PROP_FPS)
        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        duration = total / fps if fps > 0 else 0.0
        cap.release()
        return fps, width, height, total, duration
    except Exception:
        return None, None, None, None, None


async def _run_processing_job(job_id: int, video_path: str):
    """Background task: run the vision pipeline on the video."""
    from datetime import datetime, timezone

    from app.db.database import AsyncSessionLocal
    from app.vision.pipeline import InferencePipeline, PipelineConfig
    from app.vision.video_source import FileVideoSource

    logger.info("Processing job %d starting | video=%s", job_id, video_path)

    async with AsyncSessionLocal() as db:
        job = await db.get(ProcessingJob, job_id)
        if not job:
            return

        job.status = JobStatus.RUNNING
        job.started_at = datetime.now(timezone.utc)
        await db.commit()

    try:
        config = PipelineConfig(
            model_path=settings.MODEL_PATH,
            device=settings.DEVICE,
            confidence=settings.CONFIDENCE,
            iou=settings.IOU,
            frame_skip=settings.FRAME_SKIP,
        )

        source = FileVideoSource(video_path)
        source.open()
        total_frames = source.metadata.total_frames or 1

        frames_done = 0
        with InferencePipeline(config) as pipeline:
            for frame_result in pipeline.process(source):
                frames_done += 1
                if frames_done % 30 == 0:
                    progress = (frames_done / total_frames) * 100
                    async with AsyncSessionLocal() as db:
                        job = await db.get(ProcessingJob, job_id)
                        if job:
                            job.progress = progress
                            job.frames_processed = frames_done
                            await db.commit()

        source.close()

        async with AsyncSessionLocal() as db:
            job = await db.get(ProcessingJob, job_id)
            if job:
                job.status = JobStatus.COMPLETED
                job.progress = 100.0
                job.frames_processed = frames_done
                job.completed_at = datetime.now(timezone.utc)
                await db.commit()

        logger.info("Processing job %d completed | %d frames", job_id, frames_done)

    except Exception as e:
        logger.exception("Processing job %d failed: %s", job_id, e)
        async with AsyncSessionLocal() as db:
            job = await db.get(ProcessingJob, job_id)
            if job:
                job.status = JobStatus.FAILED
                job.error_message = str(e)
                await db.commit()
