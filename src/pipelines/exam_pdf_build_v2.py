"""Exam PDF Build Pipeline v2

Jinja2 + KaTeX + Playwright approach:
- Jinja2 renders a full HTML exam layout from template file
- KaTeX (loaded from CDN via auto-render) renders all LaTeX math in-browser
- Playwright headless Chromium prints the page to PDF
- Images embedded as base64 data URIs from presigned S3 URLs
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

import base64
import requests
from jinja2 import Environment, FileSystemLoader, StrictUndefined

from src.shared.base.base_pipeline import BasePipeline
from src.lib.playwright import PlaywrightManager

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Input (drop-in compatible with v1)
# ---------------------------------------------------------------------------

@dataclass
class ExamPdfBuildInput:
    exam_data: Dict[str, Any]
    presigned_urls: Dict[str, str] = field(default_factory=dict)
    school_name: str = "TRƯỜNG ĐẠI HỌC"
    subject_label: str = ""
    duration_minutes: int = 90
    include_answer_key: bool = True


# ---------------------------------------------------------------------------
# Image helpers
# ---------------------------------------------------------------------------

def _fetch_data_uri(url: str) -> Optional[str]:
    try:
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
        ct = resp.headers.get("Content-Type", "image/jpeg").split(";")[0].strip()
        b64 = base64.b64encode(resp.content).decode()
        return f"data:{ct};base64,{b64}"
    except Exception as exc:
        logger.warning("Failed to fetch image %s: %s", url, exc)
        return None


def _resolve_images(image_ids: List[str], presigned_urls: Dict[str, str]) -> List[str]:
    result: List[str] = []
    for fid in image_ids or []:
        url = presigned_urls.get(str(fid))
        if url:
            uri = _fetch_data_uri(url)
            if uri:
                result.append(uri)
    return result


# ---------------------------------------------------------------------------
# Answer helpers
# ---------------------------------------------------------------------------

_MC_LABELS = list("ABCDEF")


def _answer_label(idx: int) -> str:
    return _MC_LABELS[idx] if idx < len(_MC_LABELS) else str(idx + 1)


def _ordered_answers(answers: List[Dict], answer_order: Optional[List[int]]) -> List[Dict]:
    if answer_order and len(answer_order) == len(answers):
        return [answers[i] for i in answer_order if i < len(answers)]
    return answers


def _correct_label(answers: List[Dict], answer_order: Optional[List[int]]) -> Optional[str]:
    ordered = _ordered_answers(answers, answer_order)
    for idx, ans in enumerate(ordered):
        if ans.get("is_correct"):
            return _answer_label(idx)
    return None


def _correct_text(answers: List[Dict]) -> Optional[str]:
    correct = next((a for a in answers if a.get("is_correct")), None)
    return correct.get("value", "") if correct else None


def _remap_true_false_answer(value: str) -> str:
    """Remap English True/False to Vietnamese Đúng/Sai for true_false questions."""
    if value.strip().lower() == "true":
        return "Đúng"
    elif value.strip().lower() == "false":
        return "Sai"
    return value


# ---------------------------------------------------------------------------
# Question data preparation
# ---------------------------------------------------------------------------

def _prepare_question(q: Dict[str, Any], presigned_urls: Dict[str, str]) -> Dict[str, Any]:
    qtype = q.get("question_type", "")
    answers: List[Dict] = q.get("answers") or []
    answer_order: Optional[List[int]] = q.get("answer_order")
    sub_questions: List[Dict] = q.get("sub_questions") or []

    prepared_subs = []
    for sq in sub_questions:
        sq_answers = sq.get("answers") or []
        sq_type = sq.get("question_type", "")
        sq_order = sq.get("answer_order")
        sq_ordered = _ordered_answers(sq_answers, sq_order)
        # Apply remapping for true_false questions
        sq_answer_list = [{"label": _answer_label(i), "value": _remap_true_false_answer(a.get("value", "")) if sq_type == "true_false" else a.get("value", "")} for i, a in enumerate(sq_ordered)]
        prepared_subs.append({
            "question_type": sq_type,
            "question_text": sq.get("question_text", ""),
            "image_data_uris": _resolve_images(sq.get("image_list") or [], presigned_urls),
            "answers": sq_answer_list
            if sq_type in ("multiple_choice", "true_false", "selection") else [],
            "is_short_answer": sq_type == "short_answer",
            "is_essay": sq_type == "essay",
            "correct_label": _correct_label(sq_answers, sq_order) if sq_type in ("multiple_choice", "true_false", "selection") else None,
            "correct_text": _correct_text(sq_answers) if sq_type in ("short_answer", "essay") else None,
        })

    ordered = _ordered_answers(answers, answer_order)
    # Apply remapping for true_false questions
    answer_list = [{"label": _answer_label(i), "value": _remap_true_false_answer(a.get("value", "")) if qtype == "true_false" else a.get("value", "")} for i, a in enumerate(ordered)]
    return {
        "question_type": qtype,
        "question_text": q.get("question_text", ""),
        "image_data_uris": _resolve_images(q.get("image_list") or [], presigned_urls),
        "answers": answer_list
        if qtype in ("multiple_choice", "true_false", "selection") else [],
        "is_short_answer": qtype == "short_answer",
        "is_essay": qtype == "essay",
        "is_composite": qtype == "composite",
        "correct_label": _correct_label(answers, answer_order) if qtype in ("multiple_choice", "true_false", "selection") else None,
        "correct_text": _correct_text(answers) if qtype in ("short_answer", "essay") else None,
        "sub_questions": prepared_subs,
    }


def _prepare_sections(sections: List[Dict], presigned_urls: Dict[str, str]) -> List[Dict]:
    result = []
    for section in sorted(sections, key=lambda s: s.get("order_index", 0)):
        questions = [
            _prepare_question(q, presigned_urls)
            for q in sorted(section.get("questions", []), key=lambda x: x.get("order_count", 0))
        ]
        result.append({"name": section.get("name", ""), "questions": questions})
    return result


# ---------------------------------------------------------------------------
# Jinja2 environment
# ---------------------------------------------------------------------------

def _get_jinja_template():
    """Load Jinja2 template from file."""
    template_dir = Path(__file__).parent.parent / "templates"
    env = Environment(
        loader=FileSystemLoader(str(template_dir)),
        undefined=StrictUndefined,
        autoescape=False,
    )
    return env.get_template("exam_instance_export.html.j2")


# ---------------------------------------------------------------------------
# Pipeline
# ---------------------------------------------------------------------------

class ExamPdfBuildPipelineV2(BasePipeline[ExamPdfBuildInput, bytes]):
    """Pipeline v2: Jinja2 + KaTeX math rendering + Playwright PDF print.

    Requires PlaywrightManager to be provided (from DI container).
    """

    def __init__(self, playwright_manager: PlaywrightManager):
        self._playwright = playwright_manager
        self._template = _get_jinja_template()

    def validate(self, payload: ExamPdfBuildInput) -> None:
        if not payload.exam_data:
            raise ValueError("exam_data is required")
        if "sections" not in payload.exam_data:
            raise ValueError("exam_data must contain 'sections'")

    async def process(self, payload: ExamPdfBuildInput) -> bytes:
        exam_data = payload.exam_data
        sections = _prepare_sections(exam_data.get("sections", []), payload.presigned_urls)
        total_questions = sum(len(s["questions"]) for s in sections)

        logger.info("ExamPdfBuildV2: sections=%d total_questions=%d", len(sections), total_questions)
        html_str = self._template.render(
            school_name=exam_data.get("school_name") or payload.school_name,
            subject_label=payload.subject_label,
            duration_minutes=payload.duration_minutes,
            exam_code=exam_data.get("exam_test_code", ""),
            total_questions=total_questions,
            sections=sections,
            include_answer_key=payload.include_answer_key,
        )

        margin = {
            "top": "2.2cm",
            "bottom": "2.2cm",
            "left": "2.5cm",
            "right": "2.5cm",
        }
        return await self._playwright.render_html_to_pdf(
            html_str,
            format="A4",
            margin=margin,
            print_background=True,
        )
