"""
VisionSafe model evaluation script.

Evaluates a trained YOLO model and reports:
  - Precision, Recall, mAP50, mAP50-95 (object detection metrics)
  - Per-class metrics
  - Confusion matrix

IMPORTANT: Object detection metrics and safety event metrics are different.
  mAP50 measures whether YOLO finds objects.
  Safety event quality measures whether the system generates correct alerts.
  Both must be evaluated separately.

Usage:
    python ml/evaluate.py \\
        --model models/best.pt \\
        --data ml/configs/construction.yaml \\
        --device 0
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)-8s | %(message)s")
logger = logging.getLogger("evaluate")


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="VisionSafe model evaluation",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    p.add_argument("--model", default="models/best.pt", help="Path to trained model")
    p.add_argument("--data", default="ml/configs/construction.yaml", help="Dataset YAML")
    p.add_argument("--imgsz", type=int, default=640, help="Evaluation image size")
    p.add_argument("--batch", type=int, default=8, help="Batch size")
    p.add_argument("--device", default="cpu", help="Device")
    p.add_argument("--split", default="test", choices=["val", "test"], help="Dataset split")
    p.add_argument("--output", default="runs/evaluate", help="Output directory")
    return p.parse_args()


def main() -> int:
    args = parse_args()

    try:
        from ultralytics import YOLO
    except ImportError:
        logger.error("ultralytics not installed.")
        return 1

    model_path = Path(args.model)
    if not model_path.exists():
        logger.error("Model not found: %s", model_path)
        return 1

    logger.info("Evaluating %s on %s split...", model_path, args.split)

    model = YOLO(str(model_path))
    results = model.val(
        data=args.data,
        imgsz=args.imgsz,
        batch=args.batch,
        device=args.device,
        split=args.split,
        project=args.output,
        plots=True,
        verbose=True,
    )

    logger.info("=" * 60)
    logger.info("Evaluation Results")
    logger.info("  mAP50    : %.4f", results.box.map50)
    logger.info("  mAP50-95 : %.4f", results.box.map)
    logger.info("  Precision: %.4f", results.box.mp)
    logger.info("  Recall   : %.4f", results.box.mr)
    logger.info("Per-class AP50:")
    for i, name in enumerate(["person", "helmet", "vest", "forklift"]):
        try:
            ap50 = results.box.ap50[i]
            logger.info("    %s: %.4f", name, ap50)
        except (IndexError, TypeError):
            logger.info("    %s: N/A", name)
    logger.info("=" * 60)

    return 0


if __name__ == "__main__":
    sys.exit(main())
