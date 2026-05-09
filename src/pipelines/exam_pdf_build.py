"""Exam PDF Build Pipeline

Converts a structured exam instance dict into a PDF byte stream.

Input payload (ExamPdfBuildInput):
  - exam_data: result of ExamService.build_exam_response_data()
  - presigned_urls: {file_id: presigned_url} for all image_list items
  - school_name, subject_label, duration_minutes, include_answer_key

Output: bytes (raw PDF)

Supports:
  - Vietnamese exam layout
  - LaTeX math inline conversion to Unicode
  - Per-question-type rendering (multiple_choice, true_false, short_answer, essay, composite)
  - image_list rendering via presigned URLs
  - Answer key appendix
"""
from __future__ import annotations

import io
import logging
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import requests
from PIL import Image as PILImage
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import cm, mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    HRFlowable,
    Image,
    KeepTogether,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
)

from src.shared.base.base_pipeline import BasePipeline

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Input / Output types
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
# Font setup
# ---------------------------------------------------------------------------

_FONT_REGISTERED = False
_BASE_FONT = "Helvetica"
_BOLD_FONT = "Helvetica-Bold"


def _try_register_fonts() -> None:
    global _FONT_REGISTERED, _BASE_FONT, _BOLD_FONT
    if _FONT_REGISTERED:
        return

    import os

    candidates = [
        ("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", "DejaVuSans"),
        ("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", "DejaVuSans-Bold"),
        ("C:/Windows/Fonts/arial.ttf", "Arial"),
        ("C:/Windows/Fonts/arialbd.ttf", "Arial-Bold"),
        ("C:/Windows/Fonts/times.ttf", "Times-Regular"),
        ("C:/Windows/Fonts/timesbd.ttf", "Times-Bold"),
    ]

    regular_registered = None
    bold_registered = None

    for path, name in candidates:
        try:
            if os.path.exists(path):
                pdfmetrics.registerFont(TTFont(name, path))
                if "Bold" in name or "bd" in path.lower():
                    if bold_registered is None:
                        bold_registered = name
                else:
                    if regular_registered is None:
                        regular_registered = name
        except Exception:
            pass

    if regular_registered:
        _BASE_FONT = regular_registered
    if bold_registered:
        _BOLD_FONT = bold_registered

    _FONT_REGISTERED = True


# ---------------------------------------------------------------------------
# LaTeX → Unicode
# ---------------------------------------------------------------------------

_MATH_PATTERNS = [
    (r"\\frac\{([^}]+)\}\{([^}]+)\}", r"(\1)/(\2)"),
    (r"\^{([^}]+)}", r"^\1"),
    (r"\^([a-zA-Z0-9])", r"^\1"),
    (r"_\{([^}]+)\}", r"_\1"),
    (r"_([a-zA-Z0-9])", r"_\1"),
    (r"\\sqrt\{([^}]+)\}", r"√(\1)"),
    (r"\\times", "×"),
    (r"\\div", "÷"),
    (r"\\pm", "±"),
    (r"\\geq", "≥"),
    (r"\\leq", "≤"),
    (r"\\neq", "≠"),
    (r"\\approx", "≈"),
    (r"\\infty", "∞"),
    (r"\\alpha", "α"),
    (r"\\beta", "β"),
    (r"\\gamma", "γ"),
    (r"\\delta", "δ"),
    (r"\\pi", "π"),
    (r"\\theta", "θ"),
    (r"\\lambda", "λ"),
    (r"\\mu", "μ"),
    (r"\\sigma", "σ"),
    (r"\\omega", "ω"),
    (r"\\Delta", "Δ"),
    (r"\\Sigma", "Σ"),
    (r"\\rightarrow", "→"),
    (r"\\leftarrow", "←"),
    (r"\\Rightarrow", "⇒"),
    (r"\\cdot", "·"),
    (r"\\ldots", "…"),
    (r"\\circ", "°"),
    (r"\\[a-zA-Z]+\{([^}]*)\}", r"\1"),
    (r"\\[a-zA-Z]+", ""),
    (r"[{}]", ""),
]


def _clean_latex(text: str) -> str:
    if not text:
        return text

    def replace_math(m: re.Match) -> str:
        inner = m.group(1) if m.lastindex else m.group(0)
        for pattern, repl in _MATH_PATTERNS:
            inner = re.sub(pattern, repl, inner)
        return inner

    text = re.sub(r"\$\$(.+?)\$\$", replace_math, text, flags=re.DOTALL)
    text = re.sub(r"\$(.+?)\$", replace_math, text)
    text = re.sub(r"\\\((.+?)\\\)", replace_math, text, flags=re.DOTALL)
    text = re.sub(r"\\\[(.+?)\\\]", replace_math, text, flags=re.DOTALL)
    return text


def _escape_xml(text: str) -> str:
    text = text.replace("&", "&amp;")
    text = text.replace("<", "&lt;")
    text = text.replace(">", "&gt;")
    return text


def _render_text(text: str) -> str:
    return _escape_xml(_clean_latex(text or ""))


# ---------------------------------------------------------------------------
# Styles
# ---------------------------------------------------------------------------

def _build_styles() -> Dict[str, ParagraphStyle]:
    _try_register_fonts()
    base = _BASE_FONT
    bold = _BOLD_FONT

    return {
        "school": ParagraphStyle("school", fontName=bold, fontSize=11, leading=14, alignment=TA_CENTER, spaceAfter=2),
        "exam_title": ParagraphStyle("exam_title", fontName=bold, fontSize=14, leading=18, alignment=TA_CENTER, spaceAfter=4),
        "exam_meta": ParagraphStyle("exam_meta", fontName=base, fontSize=10, leading=14, alignment=TA_CENTER, spaceAfter=2),
        "exam_code": ParagraphStyle("exam_code", fontName=bold, fontSize=11, leading=14, alignment=TA_CENTER, spaceAfter=6),
        "section_title": ParagraphStyle("section_title", fontName=bold, fontSize=11, leading=15, spaceBefore=10, spaceAfter=4),
        "question": ParagraphStyle("question", fontName=base, fontSize=10, leading=14, alignment=TA_JUSTIFY, spaceAfter=3),
        "answer": ParagraphStyle("answer", fontName=base, fontSize=10, leading=13, leftIndent=20, spaceAfter=2),
        "sub_question": ParagraphStyle("sub_question", fontName=base, fontSize=10, leading=14, leftIndent=15, spaceAfter=3),
        "blank_line": ParagraphStyle("blank_line", fontName=base, fontSize=10, leading=14, leftIndent=20, spaceAfter=2),
        "answer_key_title": ParagraphStyle("answer_key_title", fontName=bold, fontSize=12, leading=16, alignment=TA_CENTER, spaceBefore=6, spaceAfter=6),
        "answer_key_item": ParagraphStyle("answer_key_item", fontName=base, fontSize=9, leading=12),
        "note": ParagraphStyle("note", fontName=base, fontSize=9, leading=12, alignment=TA_CENTER, textColor=colors.grey),
    }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_MC_LABELS = ["A", "B", "C", "D", "E", "F"]


def _answer_label(idx: int) -> str:
    return _MC_LABELS[idx] if idx < len(_MC_LABELS) else str(idx + 1)


def _fetch_image(url: str, max_w: float = 10 * cm, max_h: float = 7 * cm) -> Optional[Image]:
    try:
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
        buf = io.BytesIO(resp.content)
        pil = PILImage.open(buf)
        w, h = pil.size
        ratio = min(max_w / w, max_h / h, 1.0)
        buf.seek(0)
        return Image(buf, width=w * ratio, height=h * ratio)
    except Exception as exc:
        logger.warning("Failed to fetch image %s: %s", url, exc)
        return None


# ---------------------------------------------------------------------------
# Question rendering helpers
# ---------------------------------------------------------------------------

def _render_images(
    image_ids: List[str],
    presigned_urls: Dict[str, str],
    max_w: float = 10 * cm,
    max_h: float = 7 * cm,
) -> List[Any]:
    parts: List[Any] = []
    for fid in image_ids:
        url = presigned_urls.get(str(fid))
        if url:
            img = _fetch_image(url, max_w, max_h)
            if img:
                parts.append(Spacer(1, 2 * mm))
                parts.append(img)
                parts.append(Spacer(1, 2 * mm))
    return parts


def _render_answers(
    answers: List[Dict],
    answer_order: Optional[List[int]],
    qtype: str,
    styles: Dict[str, ParagraphStyle],
    indent: str = "&nbsp;&nbsp;&nbsp;",
) -> List[Any]:
    parts: List[Any] = []

    if qtype in ("multiple_choice", "true_false", "selection"):
        ordered = answers
        if answer_order and len(answer_order) == len(answers):
            ordered = [answers[i] for i in answer_order if i < len(answers)]
        for idx, ans in enumerate(ordered):
            val = _render_text(ans.get("value", ""))
            parts.append(Paragraph(f"{indent}<b>{_answer_label(idx)}.</b> {val}", styles["answer"]))

    elif qtype == "short_answer":
        parts.append(Paragraph(f"{indent}Trả lời: ____________________________", styles["blank_line"]))

    elif qtype == "essay":
        for _ in range(4):
            parts.append(Paragraph(f"{indent}____________________________________________", styles["blank_line"]))

    return parts


def _render_sub_question(
    sq: Dict[str, Any],
    label: str,
    styles: Dict[str, ParagraphStyle],
    presigned_urls: Dict[str, str],
) -> List[Any]:
    parts: List[Any] = []
    qtype = sq.get("question_type", "")
    q_text = _render_text(sq.get("question_text", ""))

    parts.append(Paragraph(f"&nbsp;&nbsp;&nbsp;&nbsp;<b>{label}</b> {q_text}", styles["sub_question"]))
    parts.extend(_render_images(sq.get("image_list") or [], presigned_urls, 8 * cm, 5 * cm))
    parts.extend(_render_answers(sq.get("answers") or [], None, qtype, styles, indent="&nbsp;" * 6))
    return parts


def _render_question(
    q: Dict[str, Any],
    q_num: int,
    styles: Dict[str, ParagraphStyle],
    presigned_urls: Dict[str, str],
) -> List[Any]:
    parts: List[Any] = []
    qtype = q.get("question_type", "")
    q_text = _render_text(q.get("question_text", ""))
    answers: List[Dict] = q.get("answers") or []
    sub_questions: List[Dict] = q.get("sub_questions") or []
    answer_order: Optional[List[int]] = q.get("answer_order")

    parts.append(Paragraph(f"<b>{q_num}.</b> {q_text}", styles["question"]))
    parts.extend(_render_images(q.get("image_list") or [], presigned_urls))

    if qtype == "composite":
        for sq_idx, sq in enumerate(sub_questions):
            parts.extend(_render_sub_question(sq, f"{q_num}.{sq_idx + 1}", styles, presigned_urls))
    else:
        parts.extend(_render_answers(answers, answer_order, qtype, styles))

    parts.append(Spacer(1, 3 * mm))
    return parts


# ---------------------------------------------------------------------------
# Answer key
# ---------------------------------------------------------------------------

def _build_answer_key(sections: List[Dict[str, Any]], styles: Dict[str, ParagraphStyle]) -> List[Any]:
    parts: List[Any] = [
        PageBreak(),
        Paragraph("BẢNG ĐÁP ÁN / ANSWER KEY", styles["answer_key_title"]),
        HRFlowable(width="100%", thickness=1, color=colors.black),
        Spacer(1, 4 * mm),
    ]

    q_num = 0
    for section in sections:
        parts.append(Paragraph(f"<b>{_escape_xml(section.get('name', ''))}</b>", styles["section_title"]))
        for q in section.get("questions", []):
            q_num += 1
            qtype = q.get("question_type", "")
            answers: List[Dict] = q.get("answers") or []
            answer_order: Optional[List[int]] = q.get("answer_order")
            sub_questions: List[Dict] = q.get("sub_questions") or []

            if qtype in ("multiple_choice", "true_false", "selection"):
                ordered = answers
                if answer_order and len(answer_order) == len(answers):
                    ordered = [answers[i] for i in answer_order if i < len(answers)]
                for idx, ans in enumerate(ordered):
                    if ans.get("is_correct"):
                        parts.append(Paragraph(f"Câu {q_num}: <b>{_answer_label(idx)}</b>", styles["answer_key_item"]))
                        break

            elif qtype in ("short_answer", "essay"):
                correct = next((a for a in answers if a.get("is_correct")), None)
                if correct:
                    parts.append(Paragraph(f"Câu {q_num}: {_render_text(correct.get('value', ''))}", styles["answer_key_item"]))

            elif qtype == "composite":
                for sq_idx, sq in enumerate(sub_questions):
                    sq_label = f"{q_num}.{sq_idx + 1}"
                    sq_answers: List[Dict] = sq.get("answers") or []
                    sq_type = sq.get("question_type", "")
                    if sq_type in ("multiple_choice", "true_false", "selection"):
                        for idx, ans in enumerate(sq_answers):
                            if ans.get("is_correct"):
                                parts.append(Paragraph(f"Câu {sq_label}: <b>{_answer_label(idx)}</b>", styles["answer_key_item"]))
                                break
                    elif sq_type in ("short_answer", "essay"):
                        correct = next((a for a in sq_answers if a.get("is_correct")), None)
                        if correct:
                            parts.append(Paragraph(f"Câu {sq_label}: {_render_text(correct.get('value', ''))}", styles["answer_key_item"]))

        parts.append(Spacer(1, 3 * mm))

    return parts


# ---------------------------------------------------------------------------
# Pipeline
# ---------------------------------------------------------------------------

class ExamPdfBuildPipeline(BasePipeline[ExamPdfBuildInput, bytes]):
    """Pipeline that converts an exam_data dict into a PDF byte stream."""

    def validate(self, payload: ExamPdfBuildInput) -> None:
        if not payload.exam_data:
            raise ValueError("exam_data is required")
        if "sections" not in payload.exam_data:
            raise ValueError("exam_data must contain 'sections'")

    async def process(self, payload: ExamPdfBuildInput) -> bytes:
        _try_register_fonts()
        styles = _build_styles()

        exam_data = payload.exam_data
        presigned_urls = payload.presigned_urls
        sections = exam_data.get("sections", [])
        exam_code = exam_data.get("exam_test_code", "")
        total_q = sum(len(s.get("questions", [])) for s in sections)

        buf = io.BytesIO()
        doc = SimpleDocTemplate(
            buf,
            pagesize=A4,
            leftMargin=2.5 * cm,
            rightMargin=2.5 * cm,
            topMargin=2 * cm,
            bottomMargin=2 * cm,
        )

        story: List[Any] = []

        # Header
        story.append(Paragraph(_escape_xml(payload.school_name), styles["school"]))
        story.append(Paragraph("ĐỀ KIỂM TRA / ĐỀ THI", styles["exam_title"]))

        meta_parts = []
        if payload.subject_label:
            meta_parts.append(f"Môn: <b>{_escape_xml(payload.subject_label)}</b>")
        meta_parts.append(f"Thời gian: <b>{payload.duration_minutes} phút</b>")
        meta_parts.append(f"Số câu: <b>{total_q}</b>")
        story.append(Paragraph(" &nbsp;|&nbsp; ".join(meta_parts), styles["exam_meta"]))
        story.append(Paragraph(f"Mã đề: <b>{_escape_xml(exam_code)}</b>", styles["exam_code"]))
        story.append(HRFlowable(width="100%", thickness=1, color=colors.black))
        story.append(Spacer(1, 4 * mm))

        # Sections + questions
        q_num = 0
        for section in sorted(sections, key=lambda s: s.get("order_index", 0)):
            story.append(Paragraph(_escape_xml(section.get("name", "")), styles["section_title"]))
            story.append(HRFlowable(width="100%", thickness=0.5, color=colors.grey))
            story.append(Spacer(1, 2 * mm))

            for q in sorted(section.get("questions", []), key=lambda x: x.get("order_count", 0)):
                q_num += 1
                block = _render_question(q, q_num, styles, presigned_urls)
                story.append(KeepTogether(block))

            story.append(Spacer(1, 5 * mm))

        story.append(Paragraph("— Hết —", styles["note"]))

        if payload.include_answer_key:
            story.extend(_build_answer_key(sections, styles))

        doc.build(story)
        buf.seek(0)
        return buf.read()
