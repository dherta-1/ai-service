"""Prepare and train YOLOv8 on PubLayNet (COCO format).

This script provides two subcommands:
1) prepare: Convert PubLayNet COCO annotations to YOLO labels.
2) train: Train a YOLOv8 model using the generated dataset YAML.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
from collections import defaultdict
from pathlib import Path

from ultralytics import YOLO


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Setup YOLOv8 + PubLayNet training for document layout detection."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    prepare = subparsers.add_parser(
        "prepare",
        help="Convert PubLayNet COCO annotations to YOLO format and build data.yaml",
    )
    prepare.add_argument(
        "--train-json",
        type=Path,
        required=True,
        help="Path to PubLayNet train annotation JSON (COCO format).",
    )
    prepare.add_argument(
        "--val-json",
        type=Path,
        required=True,
        help="Path to PubLayNet val annotation JSON (COCO format).",
    )
    prepare.add_argument(
        "--train-images",
        type=Path,
        required=True,
        help="Directory containing PubLayNet train images.",
    )
    prepare.add_argument(
        "--val-images",
        type=Path,
        required=True,
        help="Directory containing PubLayNet val images.",
    )
    prepare.add_argument(
        "--output-dir",
        type=Path,
        default=Path("data/publaynet_yolo"),
        help="Output YOLO dataset directory (default: data/publaynet_yolo).",
    )
    prepare.add_argument(
        "--copy-images",
        action="store_true",
        help="Copy images instead of trying hard links first.",
    )

    train = subparsers.add_parser("train", help="Train YOLOv8 on prepared PubLayNet.")
    train.add_argument(
        "--data",
        type=Path,
        default=Path("data/publaynet_yolo/data.yaml"),
        help="Path to YOLO data.yaml (default: data/publaynet_yolo/data.yaml).",
    )
    train.add_argument(
        "--model",
        type=str,
        default="yolov8n.pt",
        help="Pretrained YOLOv8 model to finetune (default: yolov8n.pt).",
    )
    train.add_argument("--epochs", type=int, default=50, help="Training epochs.")
    train.add_argument("--imgsz", type=int, default=1024, help="Image size.")
    train.add_argument("--batch", type=int, default=8, help="Batch size.")
    train.add_argument(
        "--device",
        type=str,
        default="0",
        help="CUDA device id or 'cpu' (default: 0).",
    )
    train.add_argument(
        "--project",
        type=Path,
        default=Path("output/yolo_train"),
        help="Training output root directory.",
    )
    train.add_argument(
        "--name",
        type=str,
        default="publaynet_yolov8",
        help="Run name under project directory.",
    )
    train.add_argument(
        "--workers", type=int, default=4, help="Number of dataloader workers."
    )

    return parser


def validate_file(path: Path, label: str) -> None:
    if not path.exists() or not path.is_file():
        raise FileNotFoundError(f"{label} not found: {path}")


def validate_dir(path: Path, label: str) -> None:
    if not path.exists() or not path.is_dir():
        raise FileNotFoundError(f"{label} not found: {path}")


def _link_or_copy(src: Path, dst: Path, copy_images: bool) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    if dst.exists():
        return

    if copy_images:
        shutil.copy2(src, dst)
        return

    try:
        os.link(src, dst)
    except OSError:
        shutil.copy2(src, dst)


def _to_yolo_bbox(
    bbox_xywh: list[float], width: float, height: float
) -> tuple[float, ...]:
    x, y, w, h = bbox_xywh
    x_center = (x + (w / 2.0)) / width
    y_center = (y + (h / 2.0)) / height
    w_norm = w / width
    h_norm = h / height

    x_center = max(0.0, min(1.0, x_center))
    y_center = max(0.0, min(1.0, y_center))
    w_norm = max(0.0, min(1.0, w_norm))
    h_norm = max(0.0, min(1.0, h_norm))

    return x_center, y_center, w_norm, h_norm


def _prepare_split(
    split_name: str,
    annotation_json: Path,
    images_dir: Path,
    output_dir: Path,
    category_id_to_idx: dict[int, int],
    copy_images: bool,
) -> tuple[int, int]:
    with annotation_json.open("r", encoding="utf-8") as f:
        coco = json.load(f)

    images = coco.get("images", [])
    annotations = coco.get("annotations", [])

    image_id_to_meta: dict[int, dict[str, object]] = {}
    for image in images:
        image_id = int(image["id"])
        image_id_to_meta[image_id] = image

    image_id_to_annotations: dict[int, list[dict[str, object]]] = defaultdict(list)
    for ann in annotations:
        if int(ann.get("iscrowd", 0)) == 1:
            continue
        image_id_to_annotations[int(ann["image_id"])].append(ann)

    split_images_dir = output_dir / "images" / split_name
    split_labels_dir = output_dir / "labels" / split_name
    split_images_dir.mkdir(parents=True, exist_ok=True)
    split_labels_dir.mkdir(parents=True, exist_ok=True)

    image_count = 0
    box_count = 0

    for image_id, meta in image_id_to_meta.items():
        file_name = str(meta["file_name"])
        width = float(meta["width"])
        height = float(meta["height"])

        src_image = images_dir / file_name
        if not src_image.exists():
            continue

        dst_image = split_images_dir / file_name
        _link_or_copy(src_image, dst_image, copy_images)

        label_path = split_labels_dir / (Path(file_name).stem + ".txt")
        label_path.parent.mkdir(parents=True, exist_ok=True)

        lines: list[str] = []
        for ann in image_id_to_annotations.get(image_id, []):
            category_id = int(ann["category_id"])
            class_idx = category_id_to_idx.get(category_id)
            if class_idx is None:
                continue

            bbox = ann.get("bbox")
            if not isinstance(bbox, list) or len(bbox) != 4:
                continue

            x_c, y_c, w_n, h_n = _to_yolo_bbox(
                [float(bbox[0]), float(bbox[1]), float(bbox[2]), float(bbox[3])],
                width=width,
                height=height,
            )
            if w_n <= 0.0 or h_n <= 0.0:
                continue

            lines.append(f"{class_idx} {x_c:.6f} {y_c:.6f} {w_n:.6f} {h_n:.6f}")
            box_count += 1

        label_path.write_text("\n".join(lines), encoding="utf-8")
        image_count += 1

    print(f"[{split_name}] prepared images: {image_count}, boxes: {box_count}")
    return image_count, box_count


def prepare_publaynet(args: argparse.Namespace) -> int:
    train_json = args.train_json.resolve()
    val_json = args.val_json.resolve()
    train_images = args.train_images.resolve()
    val_images = args.val_images.resolve()
    output_dir = args.output_dir.resolve()

    validate_file(train_json, "Train annotation JSON")
    validate_file(val_json, "Val annotation JSON")
    validate_dir(train_images, "Train images directory")
    validate_dir(val_images, "Val images directory")

    with train_json.open("r", encoding="utf-8") as f:
        train_coco = json.load(f)

    categories = train_coco.get("categories", [])
    if not categories:
        raise ValueError("No categories found in train annotation JSON")

    categories_sorted = sorted(categories, key=lambda c: int(c["id"]))
    category_id_to_idx = {
        int(cat["id"]): idx for idx, cat in enumerate(categories_sorted)
    }
    class_names = [str(cat["name"]) for cat in categories_sorted]

    print(f"Detected classes ({len(class_names)}): {', '.join(class_names)}")

    _prepare_split(
        split_name="train",
        annotation_json=train_json,
        images_dir=train_images,
        output_dir=output_dir,
        category_id_to_idx=category_id_to_idx,
        copy_images=args.copy_images,
    )
    _prepare_split(
        split_name="val",
        annotation_json=val_json,
        images_dir=val_images,
        output_dir=output_dir,
        category_id_to_idx=category_id_to_idx,
        copy_images=args.copy_images,
    )

    data_yaml = output_dir / "data.yaml"
    names_list = ", ".join([f"'{name}'" for name in class_names])
    yaml_text = (
        f"path: {output_dir.as_posix()}\n"
        "train: images/train\n"
        "val: images/val\n"
        f"nc: {len(class_names)}\n"
        f"names: [{names_list}]\n"
    )
    data_yaml.write_text(yaml_text, encoding="utf-8")

    print(f"Saved dataset YAML: {data_yaml}")
    print("Preparation complete.")
    return 0


def train_publaynet(args: argparse.Namespace) -> int:
    data_yaml = args.data.resolve()
    validate_file(data_yaml, "YOLO data.yaml")

    model = YOLO(args.model)
    model.train(
        data=str(data_yaml),
        epochs=args.epochs,
        imgsz=args.imgsz,
        batch=args.batch,
        device=args.device,
        project=str(args.project),
        name=args.name,
        workers=args.workers,
    )
    return 0


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    if args.command == "prepare":
        return prepare_publaynet(args)
    if args.command == "train":
        return train_publaynet(args)

    parser.print_help()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
