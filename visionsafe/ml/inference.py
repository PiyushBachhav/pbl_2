"""
Phase 2 CLI: Video → YOLO → Annotated Output Video

Usage:
    python ml/inference.py --input videos/sample.mp4 --output videos/output.mp4

This script validates the full vision pipeline without any backend or database.
It is the Phase 2 deliverable: visual verification that detection and tracking work.

Options:
    --input     : Path to input video file
    --output    : Path for annotated output video (default: <input>_annotated.mp4)
    --model     : YOLO model path or name (default: yolov8n.pt)
    --device    : 'cpu' or 'cuda' (default: cpu)
    --confidence: Detection confidence threshold (default: 0.35)
    --iou       : NMS IoU threshold (default: 0.5)
    --imgsz     : Inference image size (default: 640)
    --skip      : Process every Nth frame (default: 1)
    --no-warmup : Skip model warmup
    --show      : Display video while processing (requires display)
"""

from __future__ import annotations

import argparse
import logging
import sys
import time
from pathlib import Path

# Allow running from project root without installing the package
sys.path.insert(0, str(Path(__file__).parent.parent / "backend"))

from app.vision.pipeline import InferencePipeline, PipelineConfig, AnnotatedVideoWriter
from app.vision.video_source import FileVideoSource

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("inference")


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="VisionSafe Phase 2 — YOLO inference on video file",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    p.add_argument("--input", required=True, help="Input video file path")
    p.add_argument("--output", default=None, help="Output annotated video path")
    p.add_argument("--model", default="yolov8n.pt", help="YOLO model path or name")
    p.add_argument("--device", default="cpu", choices=["cpu", "cuda", "0"], help="Inference device")
    p.add_argument("--confidence", type=float, default=0.35, help="Detection confidence threshold")
    p.add_argument("--iou", type=float, default=0.5, help="NMS IoU threshold")
    p.add_argument("--imgsz", type=int, default=640, help="Inference image size")
    p.add_argument("--skip", type=int, default=1, help="Process every Nth frame")
    p.add_argument("--no-warmup", action="store_true", help="Skip model warmup")
    p.add_argument("--show", action="store_true", help="Show live annotated frames")
    return p.parse_args()


def main() -> int:
    args = parse_args()

    input_path = Path(args.input)
    if not input_path.exists():
        logger.error("Input file not found: %s", input_path)
        return 1

    # Default output path
    if args.output is None:
        output_path = input_path.parent / f"{input_path.stem}_annotated.mp4"
    else:
        output_path = Path(args.output)

    logger.info("=" * 60)
    logger.info("VisionSafe — Phase 2 Inference")
    logger.info("  Input  : %s", input_path)
    logger.info("  Output : %s", output_path)
    logger.info("  Model  : %s", args.model)
    logger.info("  Device : %s", args.device)
    logger.info("  Conf   : %.2f", args.confidence)
    logger.info("  Skip   : every %d frame(s)", args.skip)
    logger.info("=" * 60)

    config = PipelineConfig(
        model_path=args.model,
        device=args.device,
        confidence=args.confidence,
        iou=args.iou,
        imgsz=args.imgsz,
        frame_skip=args.skip,
        warmup=not args.no_warmup,
    )

    source = FileVideoSource(str(input_path), frame_skip=args.skip)

    try:
        source.open()
    except (FileNotFoundError, RuntimeError) as e:
        logger.error("Cannot open video: %s", e)
        return 1

    meta = source.metadata
    logger.info(
        "Video info | %dx%d @ %.1f fps | %d frames | %.1f sec",
        meta.width, meta.height, meta.fps,
        meta.total_frames, meta.duration_seconds,
    )

    # Stats tracking
    total_frames = 0
    total_persons = 0
    total_helmets = 0
    total_vests = 0
    total_forklifts = 0
    fps_history: list[float] = []

    t_start = time.perf_counter()

    with InferencePipeline(config) as pipeline:
        with AnnotatedVideoWriter(
            output_path=output_path,
            fps=meta.fps / args.skip,
            width=meta.width,
            height=meta.height,
        ) as writer:
            for frame_result, frame in _process_with_frame(pipeline, source):
                # Running FPS
                elapsed = time.perf_counter() - t_start
                fps = (total_frames + 1) / elapsed if elapsed > 0 else 0

                writer.write(frame, frame_result, fps=fps)

                if args.show:
                    display = _make_display_frame(frame, frame_result, fps)
                    cv2.imshow("VisionSafe", display)
                    if cv2.waitKey(1) & 0xFF == ord("q"):
                        logger.info("User interrupted.")
                        break

                # Accumulate stats
                total_frames += 1
                total_persons += len(frame_result.persons)
                total_helmets += len(frame_result.helmets)
                total_vests += len(frame_result.vests)
                total_forklifts += len(frame_result.forklifts)
                fps_history.append(frame_result.processing_time_ms)

    if args.show:
        import cv2 as cv2_local
        cv2_local.destroyAllWindows()

    # Summary
    elapsed = time.perf_counter() - t_start
    avg_fps = total_frames / elapsed if elapsed > 0 else 0
    avg_ms = sum(fps_history) / len(fps_history) if fps_history else 0

    logger.info("=" * 60)
    logger.info("Processing complete")
    logger.info("  Frames processed : %d", total_frames)
    logger.info("  Total time       : %.1f sec", elapsed)
    logger.info("  Average FPS      : %.1f", avg_fps)
    logger.info("  Avg latency      : %.1f ms/frame", avg_ms)
    logger.info("  Persons detected : %d (total across frames)", total_persons)
    logger.info("  Helmets detected : %d", total_helmets)
    logger.info("  Vests detected   : %d", total_vests)
    logger.info("  Forklifts detected: %d", total_forklifts)
    logger.info("  Output saved to  : %s", output_path)
    logger.info("=" * 60)

    source.close()
    return 0


def _process_with_frame(pipeline, source):
    """Yield (frame_result, raw_frame) pairs."""
    for frame_idx, timestamp, frame in source.frames():
        import time as time_mod
        t = time_mod.perf_counter()

        from app.vision.association import build_ppe_states
        tracked = pipeline._tracker.track(frame, frame_idx=frame_idx, timestamp=timestamp)

        persons = [t for t in tracked if t.class_name == "person"]
        helmets = [t for t in tracked if t.class_name == "helmet"]
        vests = [t for t in tracked if t.class_name == "vest"]
        ppe_states = build_ppe_states(persons, helmets, vests)

        for person in persons:
            state = ppe_states.get(person.track_id)
            if state:
                person.ppe_state = state

        from app.vision.detections import FrameResult
        ms = (time_mod.perf_counter() - t) * 1000
        frame_result = FrameResult(
            frame_idx=frame_idx,
            timestamp=timestamp,
            tracked_objects=tracked,
            processing_time_ms=ms,
        )
        yield frame_result, frame


def _make_display_frame(frame, frame_result, fps):
    """Create a display frame for --show mode."""
    import cv2
    from app.vision.annotator import draw_tracked_objects, draw_metrics
    out = frame.copy()
    ppe_map = {
        p.track_id: p.ppe_state
        for p in frame_result.persons
        if p.ppe_state
    }
    out = draw_tracked_objects(out, frame_result.tracked_objects, ppe_map)
    out = draw_metrics(
        out, fps=fps,
        inference_ms=frame_result.inference_time_ms,
        tracking_ms=frame_result.tracking_ms,
        frame_idx=frame_result.frame_idx,
    )
    return out


if __name__ == "__main__":
    sys.exit(main())
