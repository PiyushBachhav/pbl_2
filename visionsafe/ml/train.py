"""
VisionSafe model training script.

Trains a YOLO model on the construction PPE dataset.
Tuned for NVIDIA RTX 3050 4GB VRAM.

Usage:
    python ml/train.py \\
        --data ml/configs/construction.yaml \\
        --model yolov8n.pt \\
        --epochs 50 \\
        --imgsz 640 \\
        --device 0

GPU settings optimized for RTX 3050 4GB:
    - yolov8n.pt: batch=16, imgsz=640  ← recommended
    - yolov8s.pt: batch=8,  imgsz=640
    - yolov8m.pt: batch=4,  imgsz=640  ← may OOM on 4GB

Training output:
    runs/detect/visionsafe_YYYYMMDD_HHMMSS/
        weights/
            best.pt   ← use this for inference
            last.pt
        results.csv
        confusion_matrix.png
        ...

After training, copy best.pt to models/:
    cp runs/detect/.../weights/best.pt models/best.pt
"""

from __future__ import annotations

import argparse
import logging
import sys
import time
from datetime import datetime
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(message)s",
)
logger = logging.getLogger("train")


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="VisionSafe YOLO training",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    p.add_argument("--data", default="ml/configs/construction.yaml", help="Dataset YAML path")
    p.add_argument("--model", default="yolov8n.pt", help="Base model (yolov8n.pt, yolov8s.pt, etc.)")
    p.add_argument("--epochs", type=int, default=50, help="Number of training epochs")
    p.add_argument("--imgsz", type=int, default=640, help="Training image size")
    p.add_argument("--batch", type=int, default=16, help="Batch size (-1 = auto)")
    p.add_argument("--device", default="cpu", help="Training device: 'cpu', '0', '0,1'")
    p.add_argument("--workers", type=int, default=4, help="DataLoader worker processes")
    p.add_argument("--patience", type=int, default=15, help="Early stopping patience (epochs)")
    p.add_argument("--project", default="runs/detect", help="Output project directory")
    p.add_argument("--name", default=None, help="Run name (auto-generated if not set)")
    p.add_argument("--resume", default=False, action="store_true", help="Resume from last.pt")
    return p.parse_args()


def main() -> int:
    args = parse_args()

    try:
        from ultralytics import YOLO
    except ImportError:
        logger.error("ultralytics not installed. Run: pip install ultralytics")
        return 1

    run_name = args.name or f"visionsafe_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

    logger.info("=" * 60)
    logger.info("VisionSafe — YOLO Training")
    logger.info("  Dataset  : %s", args.data)
    logger.info("  Model    : %s", args.model)
    logger.info("  Epochs   : %d", args.epochs)
    logger.info("  Batch    : %d", args.batch)
    logger.info("  ImgSz    : %d", args.imgsz)
    logger.info("  Device   : %s", args.device)
    logger.info("  Workers  : %d", args.workers)
    logger.info("  Run name : %s", run_name)
    logger.info("=" * 60)

    data_path = Path(args.data)
    if not data_path.exists():
        logger.error("Dataset YAML not found: %s", data_path)
        logger.error("Please prepare your dataset first. See ml/datasets/README.md")
        return 1

    model = YOLO(args.model)

    t_start = time.time()

    results = model.train(
        data=str(data_path),
        epochs=args.epochs,
        imgsz=args.imgsz,
        batch=args.batch,
        device=args.device,
        workers=args.workers,
        patience=args.patience,
        project=args.project,
        name=run_name,
        resume=args.resume,
        # Augmentation — keep defaults which are well-tuned for detection
        # Metrics
        plots=True,
        save=True,
        save_period=10,  # Save checkpoint every 10 epochs
        val=True,
        verbose=True,
    )

    elapsed = time.time() - t_start

    logger.info("=" * 60)
    logger.info("Training complete in %.1f minutes", elapsed / 60)

    # Print final metrics
    try:
        metrics = results.results_dict
        logger.info("  mAP50    : %.4f", metrics.get("metrics/mAP50(B)", 0))
        logger.info("  mAP50-95 : %.4f", metrics.get("metrics/mAP50-95(B)", 0))
        logger.info("  Precision: %.4f", metrics.get("metrics/precision(B)", 0))
        logger.info("  Recall   : %.4f", metrics.get("metrics/recall(B)", 0))
    except Exception:
        pass

    # Locate best weights
    best_pt = Path(args.project) / run_name / "weights" / "best.pt"
    if best_pt.exists():
        logger.info("Best model: %s", best_pt)
        logger.info("Copy to models/: cp %s models/best.pt", best_pt)
    logger.info("=" * 60)

    return 0


if __name__ == "__main__":
    sys.exit(main())
