"""Quick test script for PaddleOCR on a single input image."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from paddleocr import PaddleOCR


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run PaddleOCR quick test with one input image."
    )
    parser.add_argument("image", type=Path, help="Path to input image file")
    parser.add_argument(
        "--lang",
        default="en",
        help="PaddleOCR language code (default: en)",
    )
    parser.add_argument(
        "--use-gpu",
        action="store_true",
        help="Enable GPU inference if paddlepaddle-gpu is installed",
    )
    parser.add_argument(
        "--save-json",
        type=Path,
        default=None,
        help="Optional path to save raw OCR output as JSON",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    image_path = args.image.resolve()

    if not image_path.exists() or not image_path.is_file():
        raise FileNotFoundError(f"Input image not found: {image_path}")

    ocr = PaddleOCR(
        use_doc_orientation_classify=True,
        use_doc_unwarping=False,
        use_textline_orientation=True,
        device="gpu" if args.use_gpu else "cpu",
        lang=args.lang,
        enable_mkldnn=False,
    )
    result = ocr.predict(str(image_path))

    # Determine output directory
    if args.save_json:
        output_dir = args.save_json
    else:
        # Extract hash from image path (e.g., output/<hash>/pages/page_1.png -> output/json/<hash>)
        try:
            parts = image_path.parts
            if "output" in parts:
                idx = parts.index("output")
                if idx + 1 < len(parts):
                    hash_part = parts[idx + 1]
                    output_dir = image_path.parent.parent.parent / "json" / hash_part
                else:
                    output_dir = image_path.parent / "ocr_output"
            else:
                output_dir = image_path.parent / "ocr_output"
        except (IndexError, ValueError):
            output_dir = image_path.parent / "ocr_output"

    output_dir.mkdir(parents=True, exist_ok=True)

    # Process results
    for idx, res in enumerate(result, start=1):
        res.print()
        res.save_to_json(str(output_dir))
        res.save_to_img(str(output_dir))

    print(f"Saved results to: {output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
