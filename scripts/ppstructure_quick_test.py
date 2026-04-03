"""Quick test script for PaddleOCR PPStructure (document layout + table extraction)."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from paddleocr import PPStructureV3


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run PPStructure quick test for document layout and table extraction."
    )
    parser.add_argument("image", type=Path, help="Path to input image file")
    parser.add_argument(
        "--lang",
        default="en",
        help="PPStructure language code (default: en)",
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
        help="Optional path to save structure output as JSON",
    )
    parser.add_argument(
        "--table-char-dict",
        type=Path,
        default=None,
        help="Custom character dictionary path for table recognition",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    image_path = args.image.resolve()

    if not image_path.exists() or not image_path.is_file():
        raise FileNotFoundError(f"Input image not found: {image_path}")

    # Initialize PPStructure
    ppstructure = PPStructureV3(
        use_doc_orientation_classify=True,
        use_doc_unwarping=False,
        use_textline_orientation=True,
        device="gpu",
        lang=args.lang,
        enable_mkldnn=False,
    )

    # Predict document structure
    result = ppstructure.predict(str(image_path))

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
                    output_dir = (
                        image_path.parent.parent.parent / "ppstructure" / hash_part
                    )
                else:
                    output_dir = image_path.parent / "ppstructure_output"
            else:
                output_dir = image_path.parent / "ppstructure_output"
        except (IndexError, ValueError):
            output_dir = image_path.parent / "ppstructure_output"

    output_dir.mkdir(parents=True, exist_ok=True)

    # Process results
    for idx, res in enumerate(result, start=1):
        # res is OCRResult object from PPStructure
        res.print()
        res.save_to_json(str(output_dir))
        res.save_to_img(str(output_dir))
        res.save_to_markdown(str(output_dir))

    # Also save structured output as JSON
    structured_output = {
        "input_path": str(image_path),
        "num_pages": len(result),
        "pages": [],
    }

    for page_idx, res in enumerate(result, start=1):
        page_data = {
            "page": page_idx,
            "input_path": str(res.path if hasattr(res, "path") else "unknown"),
            "model_settings": {
                "use_doc_preprocessor": False,
                "use_textline_orientation": False,
            },
            "text_elements": [],
            "tables": [],
        }

        # Extract text and structure info
        if hasattr(res, "rec_texts") and hasattr(res, "rec_scores"):
            for text_idx, (text, score) in enumerate(
                zip(res.rec_texts, res.rec_scores)
            ):
                page_data["text_elements"].append(
                    {
                        "index": text_idx,
                        "text": text,
                        "score": float(score),
                    }
                )

        # Extract table info if available
        if hasattr(res, "table_boxes"):
            for table_idx, table_box in enumerate(res.table_boxes):
                page_data["tables"].append(
                    {
                        "index": table_idx,
                        "box": (
                            table_box.tolist()
                            if hasattr(table_box, "tolist")
                            else table_box
                        ),
                    }
                )

        structured_output["pages"].append(page_data)

    structured_path = output_dir / f"{image_path.stem}_ppstructure.json"
    structured_path.write_text(
        json.dumps(structured_output, ensure_ascii=True, indent=2),
        encoding="utf-8",
    )

    print(f"Saved PPStructure results to: {output_dir}")
    print(f"Saved structured output to: {structured_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
