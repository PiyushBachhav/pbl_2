"""
Video upload and processing API routes.

POST /videos              — upload video file
GET  /videos              — list videos with job status and annotated video URL
GET  /videos/{id}         — get video details + job status
GET  /videos/{id}/annotated — download/stream annotated video
POST /videos/{id}/process — start full safety vision processing job
"""

from __future__ import annotations

import asyncio
import logging
import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, BackgroundTasks
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.config import settings
from app.db.database import get_db, AsyncSessionLocal
from app.db.models import (
    Video,
    ProcessingJob,
    JobStatus,
    Zone,
    Rule,
    SafetyEvent,
    EventEvidence,
    Severity,
    EventStatus,
)
from app.safety import (
    SafetyRuleEngine,
    TemporalEngine,
    ZoneEngine,
    ConfirmedViolation,
    EndedViolation,
)
from app.vision.annotator import save_evidence_frame
from app.vision.pipeline import InferencePipeline, PipelineConfig, AnnotatedVideoWriter
from app.vision.video_source import FileVideoSource
from app.websocket import ws_manager

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/videos", tags=["videos"])

ALLOWED_EXTENSIONS = {".mp4", ".avi", ".mkv", ".mov", ".webm"}


def _get_annotated_info(video: Video) -> tuple[Optional[str], Optional[str]]:
    """Return (file_path, url_path) if annotated video exists."""
    annotated_filename = f"{Path(video.filename).stem}_annotated.mp4"
    annotated_path = settings.video_path / annotated_filename
    if annotated_path.exists():
        return str(annotated_path), f"/videos/{annotated_filename}"
    return None, None


@router.get("/", response_model=list[dict])
async def list_videos(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Video).order_by(Video.created_at.desc()))
    videos = result.scalars().all()
    out = []
    for v in videos:
        _, ann_url = _get_annotated_info(v)
        job = v.job
        out.append({
            "id": v.id,
            "filename": v.original_filename,
            "fps": v.fps,
            "duration_seconds": v.duration_seconds,
            "width": v.width,
            "height": v.height,
            "total_frames": v.total_frames,
            "annotated_video_url": ann_url,
            "job": {
                "status": job.status.value if job else None,
                "progress": job.progress if job else None,
                "fps_achieved": job.fps_achieved if job else None,
                "error": job.error_message if job else None,
            } if job else None,
        })
    return out


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

    return {
        "id": video.id,
        "filename": video.filename,
        "original_filename": file.filename,
        "duration_seconds": duration,
        "fps": fps,
        "width": width,
        "height": height,
        "total_frames": total_frames,
    }


@router.get("/{video_id}", response_model=dict)
async def get_video(video_id: int, db: AsyncSession = Depends(get_db)):
    video = await db.get(Video, video_id)
    if not video:
        raise HTTPException(status_code=404, detail="Video not found")

    job = video.job
    _, ann_url = _get_annotated_info(video)
    return {
        "id": video.id,
        "filename": video.original_filename,
        "fps": video.fps,
        "duration_seconds": video.duration_seconds,
        "width": video.width,
        "height": video.height,
        "total_frames": video.total_frames,
        "annotated_video_url": ann_url,
        "job": {
            "status": job.status.value if job else None,
            "progress": job.progress if job else None,
            "fps_achieved": job.fps_achieved if job else None,
            "error": job.error_message if job else None,
        } if job else None,
    }


@router.get("/{video_id}/annotated")
async def get_annotated_video(video_id: int, db: AsyncSession = Depends(get_db)):
    """Stream or download the processed annotated video."""
    video = await db.get(Video, video_id)
    if not video:
        raise HTTPException(status_code=404, detail="Video not found")

    ann_path, _ = _get_annotated_info(video)
    if not ann_path or not Path(ann_path).exists():
        raise HTTPException(status_code=404, detail="Annotated video not found or not yet processed")

    return FileResponse(
        path=ann_path,
        media_type="video/mp4",
        filename=f"annotated_{video.original_filename}",
    )


@router.post("/{video_id}/process", response_model=dict, status_code=202)
async def start_processing(
    video_id: int,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
):
    """Start background safety intelligence processing job for a video."""
    video = await db.get(Video, video_id)
    if not video:
        raise HTTPException(status_code=404, detail="Video not found")

    # Check existing job
    if video.job and video.job.status == JobStatus.RUNNING:
        raise HTTPException(status_code=409, detail="Processing already running")

    if video.job:
        job = video.job
        job.status = JobStatus.PENDING
        job.progress = 0.0
        job.frames_processed = 0
        job.error_message = None
    else:
        job = ProcessingJob(video_id=video.id, status=JobStatus.PENDING)
        db.add(job)

    await db.flush()
    await db.refresh(job)

    job_id = job.id
    background_tasks.add_task(_run_processing_job, job_id, video.id)

    logger.info("Processing job %d queued for video %d", job_id, video_id)
    return {"job_id": job_id, "status": "PENDING", "message": "Processing started"}


# ─────────────────────────────────────────
# Helpers & Background Pipeline Runner
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


async def _run_processing_job(job_id: int, video_id: int):
    """
    Background worker:
    Executes the full end-to-end vision pipeline:
      Video → YOLO detection + BoT-SORT tracking → PPE association
            → Zone Engine & Safety Rule Engine evaluation
            → Temporal persistence filtering
            → DB SafetyEvent & EventEvidence creation
            → Real-time WebSocket broadcasting
            → Output annotated video generation
    """
    logger.info("Processing job %d starting for video %d", job_id, video_id)

    # 1. Update job to RUNNING and fetch video & configuration
    async with AsyncSessionLocal() as db:
        job = await db.get(ProcessingJob, job_id)
        video = await db.get(Video, video_id)
        if not job or not video:
            logger.error("Job %d or Video %d not found in database", job_id, video_id)
            return

        job.status = JobStatus.RUNNING
        job.started_at = datetime.now(timezone.utc)
        await db.commit()

        video_path = video.file_path
        camera_id = video.camera_id

        # Load active zones for this camera (or all zones if no camera linked)
        zone_query = select(Zone).where(Zone.enabled.is_(True))
        if camera_id:
            zone_query = zone_query.where((Zone.camera_id == camera_id) | (Zone.camera_id.is_(None)))
        zone_results = (await db.execute(zone_query)).scalars().all()

        zone_dicts = [
            {
                "id": z.id,
                "name": z.name,
                "polygon": z.polygon,
                "zone_type": z.zone_type.value,
                "severity": z.severity.value,
                "color": z.color or "#FF4444",
                "required_ppe": z.required_ppe or ["helmet", "vest"],
                "enabled": z.enabled,
            }
            for z in zone_results
        ]

        # Load active safety rules
        rule_results = (await db.execute(select(Rule).where(Rule.enabled.is_(True)))).scalars().all()
        rules_list = list(rule_results)

    # 2. Setup engines
    zone_engine = ZoneEngine()
    rule_engine = SafetyRuleEngine(rules=rules_list, zone_engine=zone_engine)
    temporal_engine = TemporalEngine(default_threshold=1.5, grace_period_seconds=1.0)

    # Output paths
    output_annotated_name = f"{Path(video_path).stem}_annotated.mp4"
    output_annotated_path = settings.video_path / output_annotated_name

    source = FileVideoSource(video_path, frame_skip=settings.FRAME_SKIP)

    try:
        source.open()
        meta = source.metadata
        total_frames = meta.total_frames or 1
        fps = meta.fps or 25.0
        width = meta.width or 1280
        height = meta.height or 720

        # Pipeline config
        config = PipelineConfig(
            model_path=settings.MODEL_PATH,
            device=settings.DEVICE,
            confidence=settings.CONFIDENCE,
            iou=settings.IOU,
            frame_skip=settings.FRAME_SKIP,
        )

        writer = AnnotatedVideoWriter(
            output_path=output_annotated_path,
            fps=fps,
            width=width,
            height=height,
        )
        writer.open()

        frames_done = 0
        t_start_total = asyncio.get_event_loop().time()
        fps_tracker = 0.0

        with InferencePipeline(config) as pipeline:
            for frame_result in pipeline.process(source):
                frames_done += 1
                curr_frame = source.last_frame if hasattr(source, "last_frame") and source.last_frame is not None else None
                # Fallback: if last_frame not cached, use blank or skip drawing
                if curr_frame is None:
                    continue

                timestamp = frame_result.timestamp or (frames_done / fps)
                frame_idx = frame_result.frame_idx

                # --- 1. Evaluate safety rules on frame ---
                raw_violations = rule_engine.evaluate(frame_result, zones=zone_dicts)

                # --- 2. Temporal persistence filtering ---
                newly_confirmed, ended_violations = temporal_engine.update(
                    current_violations=raw_violations,
                    timestamp=timestamp,
                    frame_idx=frame_idx,
                )

                # --- 3. Handle newly confirmed safety violations ---
                active_banners = [
                    {"description": v.description, "severity": v.severity}
                    for v in raw_violations[:3]
                ]
                proximity_events = [
                    v.metadata for v in raw_violations if v.rule_type == "FORKLIFT_PROXIMITY"
                ]

                # Draw annotated frame for video & potential evidence capture
                annotated_frame = writer.write(
                    frame=curr_frame,
                    frame_result=frame_result,
                    fps=fps_tracker,
                    zones=zone_dicts,
                    events=active_banners,
                    proximity_events=proximity_events,
                )

                if newly_confirmed:
                    async with AsyncSessionLocal() as db:
                        for conf in newly_confirmed:
                            # Generate unique evidence file
                            evidence_filename = (
                                f"evidence_v{video_id}_f{frame_idx}_{conf.rule_type.lower()}_{uuid.uuid4().hex[:6]}.jpg"
                            )
                            evidence_dest = settings.evidence_path / evidence_filename
                            save_evidence_frame(
                                frame=annotated_frame,
                                path=str(evidence_dest),
                                event_description=conf.description,
                                severity=conf.severity,
                            )

                            evt = SafetyEvent(
                                video_id=video_id,
                                camera_id=camera_id,
                                rule_id=conf.rule_id,
                                zone_id=conf.zone_id,
                                event_type=conf.rule_type,
                                severity=Severity(conf.severity),
                                status=EventStatus.OPEN,
                                subject_track_id=conf.subject_track_id,
                                related_track_id=conf.related_track_id,
                                confidence=conf.confidence,
                                description=conf.description,
                                evidence_frame_path=f"/evidence/{evidence_filename}",
                                event_metadata=conf.metadata,
                            )
                            db.add(evt)
                            await db.flush()
                            await db.refresh(evt)

                            conf.state.db_event_id = evt.id

                            # Add evidence record
                            evidence_rec = EventEvidence(
                                event_id=evt.id,
                                frame_path=f"/evidence/{evidence_filename}",
                                frame_number=frame_idx,
                                timestamp=timestamp,
                            )
                            db.add(evidence_rec)
                            await db.commit()

                            # Broadcast alert via WebSocket to live dashboard
                            await ws_manager.broadcast({
                                "type": "SAFETY_EVENT",
                                "event": {
                                    "id": evt.id,
                                    "event_type": evt.event_type,
                                    "severity": evt.severity.value,
                                    "description": evt.description,
                                    "subject_track_id": evt.subject_track_id,
                                    "related_track_id": evt.related_track_id,
                                    "zone_id": evt.zone_id,
                                    "detected_at": datetime.now(timezone.utc).isoformat(),
                                    "evidence_frame_path": evt.evidence_frame_path,
                                },
                            })

                # --- 4. Handle ended violations (update duration) ---
                if ended_violations:
                    async with AsyncSessionLocal() as db:
                        for ended in ended_violations:
                            if ended.db_event_id:
                                evt = await db.get(SafetyEvent, ended.db_event_id)
                                if evt:
                                    evt.ended_at = datetime.now(timezone.utc)
                                    evt.duration_seconds = round(ended.duration_seconds, 2)
                        await db.commit()

                # --- 5. Periodic progress update ---
                if frames_done % 20 == 0 or frames_done == total_frames:
                    elapsed = asyncio.get_event_loop().time() - t_start_total
                    fps_tracker = frames_done / elapsed if elapsed > 0 else 0.0
                    progress = min(99.0, (frames_done / total_frames) * 100)

                    async with AsyncSessionLocal() as db:
                        job = await db.get(ProcessingJob, job_id)
                        if job:
                            job.progress = progress
                            job.frames_processed = frames_done
                            job.fps_achieved = round(fps_tracker, 1)
                            await db.commit()

                    # Broadcast progress
                    await ws_manager.broadcast({
                        "type": "JOB_PROGRESS",
                        "video_id": video_id,
                        "job_id": job_id,
                        "progress": round(progress, 1),
                        "fps": round(fps_tracker, 1),
                        "frames_processed": frames_done,
                        "total_frames": total_frames,
                    })

        # --- 6. Cleanup remaining open violations ---
        ended_final = temporal_engine.flush_all(final_timestamp=total_frames / fps)
        if ended_final:
            async with AsyncSessionLocal() as db:
                for ended in ended_final:
                    if ended.db_event_id:
                        evt = await db.get(SafetyEvent, ended.db_event_id)
                        if evt:
                            evt.ended_at = datetime.now(timezone.utc)
                            evt.duration_seconds = round(ended.duration_seconds, 2)
                await db.commit()

        writer.close()
        source.close()

        # --- 7. Mark Job Completed ---
        elapsed_total = asyncio.get_event_loop().time() - t_start_total
        final_fps = frames_done / elapsed_total if elapsed_total > 0 else 0.0

        async with AsyncSessionLocal() as db:
            job = await db.get(ProcessingJob, job_id)
            if job:
                job.status = JobStatus.COMPLETED
                job.progress = 100.0
                job.frames_processed = frames_done
                job.fps_achieved = round(final_fps, 1)
                job.completed_at = datetime.now(timezone.utc)
                await db.commit()

        await ws_manager.broadcast({
            "type": "JOB_COMPLETED",
            "video_id": video_id,
            "job_id": job_id,
            "annotated_video_url": f"/videos/{output_annotated_name}",
        })

        logger.info(
            "Processing job %d completed | %d frames in %.1fs (%.1f FPS) | annotated=%s",
            job_id, frames_done, elapsed_total, final_fps, output_annotated_name,
        )

    except Exception as e:
        logger.exception("Processing job %d failed: %s", job_id, e)
        try:
            source.close()
        except Exception:
            pass
        async with AsyncSessionLocal() as db:
            job = await db.get(ProcessingJob, job_id)
            if job:
                job.status = JobStatus.FAILED
                job.error_message = str(e)
                await db.commit()

        await ws_manager.broadcast({
            "type": "JOB_FAILED",
            "video_id": video_id,
            "job_id": job_id,
            "error": str(e),
        })
