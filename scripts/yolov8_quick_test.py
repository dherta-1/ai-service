"""Quick test script for YOLOv8 layout/object detection on one image."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from PIL import Image
from ultralytics import YOLO


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run YOLOv8 quick test with one input image."
    )
    parser.add_argument("image", type=Path, help="Path to input image file")
    parser.add_argument(
        "--model",
        type=str,
        default="yolov8n.pt",
        help="YOLO model path/name (default: yolov8n.pt)",
    )
    parser.add_argument(
        "--conf",
        type=float,
        default=0.25,
        help="Confidence threshold (default: 0.25)",
    )
    parser.add_argument(
        "--save-image",
        type=Path,
        default=None,
        help="Optional path to save rendered detection image",
    )
    parser.add_argument(
        "--save-json",
        type=Path,
        default=None,
        help="Optional path to save detections as JSON",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    image_path = args.image.resolve()

    if not image_path.exists() or not image_path.is_file():
        raise FileNotFoundError(f"Input image not found: {image_path}")

    model = YOLO(args.model)
    results = model.predict(source=str(image_path), conf=args.conf, verbose=False)

    if not results:
        print("No prediction result returned")
        return 0

    first = results[0]
    names = first.names
    boxes = first.boxes
    detection_count = len(boxes)
    print(f"Detected {detection_count} objects")

    json_rows: list[dict[str, object]] = []
    for idx, box in enumerate(boxes, start=1):
        cls_id = int(box.cls.item())
        conf = float(box.conf.item())
        xyxy = [float(v) for v in box.xyxy[0].tolist()]
        label = names.get(cls_id, str(cls_id))

        row = {
            "index": idx,
            "class_id": cls_id,
            "label": label,
            "confidence": conf,
            "xyxy": xyxy,
        }
        json_rows.append(row)

        print(
            f"[{idx:03d}] class={label}({cls_id}) conf={conf:.4f} "
            f"box={json.dumps(xyxy, ensure_ascii=True)}"
        )

    if args.save_image:
        rendered = first.plot()
        # Handle both directory and file paths
        save_path = Path(args.save_image)
        if not save_path.suffix:  # No file extension, treat as directory
            save_path = save_path / f"{image_path.stem}_yolo.png"
        save_path.parent.mkdir(parents=True, exist_ok=True)
        Image.fromarray(rendered).save(str(save_path))
        print(f"Saved detection image to: {save_path}")

    if args.save_json:
        save_path = Path(args.save_json)
        if not save_path.suffix:  # No file extension, treat as directory
            save_path = save_path / f"{image_path.stem}_yolo.json"
        save_path.parent.mkdir(parents=True, exist_ok=True)
        save_path.write_text(
            json.dumps(json_rows, ensure_ascii=True, indent=2),
            encoding="utf-8",
        )
        print(f"Saved detections JSON to: {save_path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
