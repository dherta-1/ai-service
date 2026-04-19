"""Mapper utilities for converting PPStructure output to OCR DTOs."""

from __future__ import annotations

import math
from typing import Any

from src.ocr.dtos import BBoxRect, OCRExtractionResult, OCRItem, OCRPageResult


def map_ppstructure_results(
    image_path: str, raw_pages: list[dict[str, Any]]
) -> OCRExtractionResult:
    """Map PPStructure pages into normalized OCR extraction result."""
    pages: list[OCRPageResult] = []
    for page_idx, raw_page in enumerate(raw_pages):
        pages.append(_map_page(raw_page, page_idx))
    return OCRExtractionResult(image_path=image_path, pages=pages)


def _map_page(raw_page: dict[str, Any], page_idx: int) -> OCRPageResult:
    raw_page = _unwrap_page_payload(raw_page)

    parsing_blocks = _get(raw_page, "parsing_res_list", []) or []
    layout_det_res = _get(raw_page, "layout_det_res", {}) or {}
    layout_boxes = _get(layout_det_res, "boxes", []) or []
    overall_ocr_res = _get(raw_page, "overall_ocr_res", {}) or {}
    formula_res_list = _get(raw_page, "formula_res_list", []) or []

    parsing_like_blocks = _normalize_parsing_blocks(
        parsing_blocks=parsing_blocks,
        layout_boxes=layout_boxes,
        overall_ocr_res=overall_ocr_res,
        formula_res_list=formula_res_list,
    )

    page_result = OCRPageResult(
        page_index=int(_get(raw_page, "page_index") or page_idx),
        width=_safe_int(_get(raw_page, "width")),
        height=_safe_int(_get(raw_page, "height")),
        raw=raw_page,
    )

    for block in parsing_like_blocks:
        bbox_values = _to_coord_sequence(
            _get(block, "block_bbox") or _get(block, "bbox")
        )
        if bbox_values is None or len(bbox_values) != 4:
            continue

        bbox = BBoxRect.from_sequence(bbox_values)
        raw_label = (
            str(_get(block, "block_label") or _get(block, "label") or "text")
            .strip()
            .lower()
        )
        content_type = _normalize_content_type(raw_label)
        content = str(_get(block, "block_content") or _get(block, "content") or "")
        accuracy = _match_layout_score(bbox, raw_label, layout_boxes)

        page_result.items.append(
            OCRItem(
                bbox=bbox,
                content=content,
                content_type=content_type,
                accuracy=accuracy,
                source_label=raw_label,
            )
        )

    return page_result


def _normalize_content_type(label: str) -> str:
    normalized = label.strip().lower()
    if normalized == "seal":
        return "seal"
    if normalized == "table":
        return "table"
    if normalized in {"formula", "equation", "math"}:
        return "formula"
    if normalized in {"image", "figure", "chart", "graphic"}:
        return "image"
    return "text"


def _match_layout_score(
    block_bbox: BBoxRect, raw_label: str, layout_boxes: list[dict[str, Any]]
) -> float:
    """Find best confidence score by IoU, preferring same-label matches."""
    candidates = []
    fallback = []

    for box in layout_boxes:
        coord = _to_coord_sequence(_get(box, "coordinate"))
        if coord is None or len(coord) != 4:
            continue
        bbox = BBoxRect.from_sequence(coord)
        iou = _iou(block_bbox, bbox)
        if iou <= 0.0:
            continue
        score = _safe_float(_get(box, "score"), 0.0)
        label = str(_get(box, "label") or "").strip().lower()

        if label == raw_label:
            candidates.append((iou, score))
        else:
            fallback.append((iou, score))

    best = max(candidates, default=None, key=lambda item: item[0])
    if best is not None:
        return float(best[1])

    alt = max(fallback, default=None, key=lambda item: item[0])
    if alt is not None:
        return float(alt[1])

    return 0.0


def _iou(a: BBoxRect, b: BBoxRect) -> float:
    x_left = max(a.x1, b.x1)
    y_top = max(a.y1, b.y1)
    x_right = min(a.x2, b.x2)
    y_bottom = min(a.y2, b.y2)

    inter_w = max(0.0, x_right - x_left)
    inter_h = max(0.0, y_bottom - y_top)
    intersection = inter_w * inter_h
    if math.isclose(intersection, 0.0):
        return 0.0

    area_a = max(0.0, a.x2 - a.x1) * max(0.0, a.y2 - a.y1)
    area_b = max(0.0, b.x2 - b.x1) * max(0.0, b.y2 - b.y1)
    denominator = area_a + area_b - intersection
    if math.isclose(denominator, 0.0):
        return 0.0
    return intersection / denominator


def _safe_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _get(source: Any, key: str, default: Any = None) -> Any:
    if source is None:
        return default

    if isinstance(source, dict):
        return source.get(key, default)

    getter = getattr(source, "get", None)
    if callable(getter):
        try:
            return getter(key, default)
        except TypeError:
            # Some custom mapping-like objects accept only one argument.
            value = getter(key)
            return default if value is None else value

    return getattr(source, key, default)


def _to_coord_sequence(value: Any) -> list[float] | None:
    if value is None:
        return None

    if hasattr(value, "tolist"):
        value = value.tolist()

    if isinstance(value, tuple):
        value = list(value)

    if not isinstance(value, list) or len(value) != 4:
        return None

    try:
        return [float(v) for v in value]
    except (TypeError, ValueError):
        return None


def _unwrap_page_payload(raw_page: Any) -> Any:
    """Normalize PPStructure page payloads that may be wrapped in a `res` field."""
    wrapped = _get(raw_page, "res")
    if wrapped is None:
        return raw_page
    return wrapped


def _normalize_parsing_blocks(
    parsing_blocks: Any,
    layout_boxes: Any,
    overall_ocr_res: Any,
    formula_res_list: Any,
) -> list[dict[str, Any]]:
    # Standard route: use existing parsing results.
    if isinstance(parsing_blocks, list) and parsing_blocks:
        normalized: list[dict[str, Any]] = []
        for block in parsing_blocks:
            bbox = _to_coord_sequence(_get(block, "block_bbox") or _get(block, "bbox"))
            if bbox is None:
                continue
            normalized.append(
                {
                    "block_label": _get(block, "block_label")
                    or _get(block, "label", "text"),
                    "block_content": _get(block, "block_content")
                    or _get(block, "content", ""),
                    "block_bbox": bbox,
                }
            )
        if normalized:
            return normalized

    # Fallback route: synthesize blocks from layout detections + OCR/formula outputs.
    normalized_boxes = _normalize_layout_boxes(layout_boxes)
    if not normalized_boxes:
        return []

    text_candidates = _normalize_overall_ocr_candidates(overall_ocr_res)
    formula_candidates = _normalize_formula_candidates(formula_res_list)

    fallback_blocks: list[dict[str, Any]] = []
    for item in normalized_boxes:
        bbox = item["bbox"]
        label = str(item["label"] or "text").strip().lower()

        if label in {"formula", "equation", "math"}:
            content = _best_candidate_text(bbox, formula_candidates)
        elif label in {"text", "number"}:
            content = _join_candidate_texts(bbox, text_candidates)
        else:
            content = ""

        fallback_blocks.append(
            {
                "block_label": label,
                "block_content": content,
                "block_bbox": bbox,
            }
        )

    return fallback_blocks


def _normalize_layout_boxes(layout_boxes: Any) -> list[dict[str, Any]]:
    if not isinstance(layout_boxes, list):
        return []
    normalized: list[dict[str, Any]] = []
    for box in layout_boxes:
        bbox = _to_coord_sequence(_get(box, "coordinate"))
        if bbox is None:
            continue
        normalized.append(
            {
                "bbox": bbox,
                "label": str(_get(box, "label") or "text").strip().lower(),
                "score": _safe_float(_get(box, "score"), 0.0),
            }
        )
    return normalized


def _normalize_overall_ocr_candidates(overall_ocr_res: Any) -> list[dict[str, Any]]:
    rec_boxes = _get(overall_ocr_res, "rec_boxes") or []
    rec_texts = _get(overall_ocr_res, "rec_texts") or []
    rec_scores = _get(overall_ocr_res, "rec_scores") or []

    candidates: list[dict[str, Any]] = []
    for idx, rec_box in enumerate(rec_boxes):
        bbox = _to_coord_sequence(rec_box)
        if bbox is None:
            continue
        text = str(rec_texts[idx]) if idx < len(rec_texts) else ""
        score = _safe_float(rec_scores[idx], 0.0) if idx < len(rec_scores) else 0.0
        candidates.append({"bbox": bbox, "text": text, "score": score})
    return candidates


def _normalize_formula_candidates(formula_res_list: Any) -> list[dict[str, Any]]:
    if not isinstance(formula_res_list, list):
        return []

    candidates: list[dict[str, Any]] = []
    for item in formula_res_list:
        bbox = _to_coord_sequence(_get(item, "dt_polys"))
        if bbox is None:
            continue
        text = str(_get(item, "rec_formula") or "")
        candidates.append({"bbox": bbox, "text": text})
    return candidates


def _best_candidate_text(
    target_bbox: list[float], candidates: list[dict[str, Any]]
) -> str:
    target = BBoxRect.from_sequence(target_bbox)
    best_text = ""
    best_iou = 0.0
    for cand in candidates:
        cand_bbox = _to_coord_sequence(cand.get("bbox"))
        if cand_bbox is None:
            continue
        iou = _iou(target, BBoxRect.from_sequence(cand_bbox))
        if iou > best_iou:
            best_iou = iou
            best_text = str(cand.get("text") or "")
    return best_text


def _join_candidate_texts(
    target_bbox: list[float], candidates: list[dict[str, Any]]
) -> str:
    target = BBoxRect.from_sequence(target_bbox)
    matched: list[tuple[float, str]] = []
    for cand in candidates:
        cand_bbox = _to_coord_sequence(cand.get("bbox"))
        if cand_bbox is None:
            continue
        iou = _iou(target, BBoxRect.from_sequence(cand_bbox))
        if iou <= 0.0:
            continue
        score = _safe_float(cand.get("score"), 0.0)
        text = str(cand.get("text") or "")
        if text:
            matched.append((score, text))

    if not matched:
        return ""
    matched.sort(key=lambda item: item[0], reverse=True)
    return " ".join(text for _, text in matched)
