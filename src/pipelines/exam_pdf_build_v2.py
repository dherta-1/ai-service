"""Exam PDF Build Pipeline v2

Jinja2 + KaTeX + Playwright approach:
- Jinja2 renders a full HTML exam layout
- KaTeX (loaded from CDN via auto-render) renders all LaTeX math in-browser
- Playwright headless Chromium prints the page to PDF
- Images embedded as base64 data URIs from presigned S3 URLs
"""
from __future__ import annotations

import asyncio
import base64
import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import requests
from jinja2 import Environment, StrictUndefined
from playwright.async_api import async_playwright

from src.shared.base.base_pipeline import BasePipeline

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
# HTML template
# ---------------------------------------------------------------------------

_TEMPLATE_SRC = r"""<!DOCTYPE html>
<html lang="vi">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">

  <!-- KaTeX -->
  <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/katex@0.16.11/dist/katex.min.css">
  <script defer src="https://cdn.jsdelivr.net/npm/katex@0.16.11/dist/katex.min.js"></script>
  <script defer src="https://cdn.jsdelivr.net/npm/katex@0.16.11/dist/contrib/auto-render.min.js"
          onload="renderMathInElement(document.body, {
            delimiters: [
              {left: '$$', right: '$$', display: true},
              {left: '\\[', right: '\\]', display: true},
              {left: '$', right: '$', display: false},
              {left: '\\(', right: '\\)', display: false}
            ],
            throwOnError: false
          });"></script>

  <style>
    @page { size: A4; margin: 2.2cm 2.5cm; }

    * { box-sizing: border-box; }

    body {
      font-family: "Times New Roman", Times, serif;
      font-size: 11pt;
      line-height: 1.6;
      color: #111;
      margin: 0;
      padding: 0;
    }

    /* Header */
    .header {
      text-align: center;
      border-bottom: 2px solid #000;
      padding-bottom: 10px;
      margin-bottom: 14px;
    }
    .school-name { font-size: 13pt; font-weight: bold; margin: 0 0 2px; }
    .exam-title  { font-size: 16pt; font-weight: bold; margin: 4px 0; text-transform: uppercase; letter-spacing: 1px; }
    .exam-meta   { font-size: 10pt; color: #333; margin: 3px 0; }
    .exam-code   { font-size: 12pt; font-weight: bold; margin: 4px 0 0; letter-spacing: 2px; }

    /* Sections */
    .section { margin-top: 16px; }
    .section-title {
      font-weight: bold;
      font-size: 11.5pt;
      border-bottom: 1px solid #888;
      padding-bottom: 3px;
      margin-bottom: 8px;
      text-transform: uppercase;
    }

    /* Questions */
    .question-block {
      margin-bottom: 12px;
      page-break-inside: avoid;
    }
    .question-text { text-align: justify; margin-bottom: 5px; }

    /* Images */
    .question-images { margin: 6px 0; text-align: center; }
    .question-images img {
      max-width: 60%;
      max-height: 200px;
      margin: 3px 6px;
      display: inline-block;
    }

    /* MC answers — 2-column grid */
    .answers-grid {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 2px 16px;
      margin: 4px 0 4px 24px;
    }
    .answer-choice { display: flex; gap: 4px; }

    /* Short answer / essay */
    .answer-blank {
      margin: 4px 0 4px 24px;
      font-style: italic;
      color: #555;
    }
    .essay-lines { margin: 4px 0 4px 24px; }
    .essay-line {
      border-bottom: 1px solid #bbb;
      height: 22px;
      margin-bottom: 4px;
    }

    /* Composite sub-questions */
    .sub-question {
      margin: 5px 0 5px 28px;
      page-break-inside: avoid;
    }
    .sub-question-text { margin-bottom: 3px; }
    .sub-answers-grid {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 2px 16px;
      margin-left: 16px;
    }

    /* Footer */
    .exam-footer {
      text-align: center;
      margin-top: 20px;
      font-style: italic;
      color: #666;
      font-size: 10pt;
    }

    /* Answer key */
    .answer-key-page {
      page-break-before: always;
      padding-top: 4px;
    }
    .answer-key-title {
      text-align: center;
      font-size: 14pt;
      font-weight: bold;
      border-bottom: 2px solid #000;
      padding-bottom: 8px;
      margin-bottom: 14px;
      text-transform: uppercase;
    }
    .answer-key-section { margin-bottom: 12px; }
    .answer-key-section-title {
      font-weight: bold;
      font-size: 10.5pt;
      margin-bottom: 5px;
    }
    .answer-key-grid {
      display: grid;
      grid-template-columns: repeat(5, 1fr);
      gap: 3px 10px;
    }
    .answer-key-item { font-size: 10pt; }

    /* KaTeX display math centering */
    .katex-display { margin: 4px 0; }
  </style>
</head>
<body>

{# ── HEADER ── #}
<div class="header">
  <p class="school-name">{{ school_name | e }}</p>
  <p class="exam-title">Đề Kiểm Tra / Đề Thi</p>
  <p class="exam-meta">
    {% if subject_label %}Môn: <strong>{{ subject_label | e }}</strong> &nbsp;·&nbsp; {% endif %}
    Thời gian: <strong>{{ duration_minutes }} phút</strong>
    &nbsp;·&nbsp; Số câu: <strong>{{ total_questions }}</strong>
  </p>
  {% if exam_code %}
  <p class="exam-code">Mã đề: {{ exam_code | e }}</p>
  {% endif %}
</div>

{# ── SECTIONS / QUESTIONS ── #}
{% set q = namespace(n=0) %}
{% for section in sections %}
<div class="section">
  <div class="section-title">{{ section.name | e }}</div>

  {% for question in section.questions %}
    {% set q.n = q.n + 1 %}
    <div class="question-block">

      {# Question text — passed raw so KaTeX can parse math #}
      <div class="question-text">
        <strong>{{ q.n }}.</strong> {{ question.question_text | e }}
      </div>

      {# Images #}
      {% if question.image_data_uris %}
      <div class="question-images">
        {% for uri in question.image_data_uris %}
        <img src="{{ uri }}" alt="question image">
        {% endfor %}
      </div>
      {% endif %}

      {# Composite: sub-questions #}
      {% if question.is_composite %}
        {% for sq in question.sub_questions %}
        <div class="sub-question">
          <div class="sub-question-text">
            <strong>{{ q.n }}.{{ loop.index }}.</strong> {{ sq.question_text | e }}
          </div>
          {% if sq.image_data_uris %}
          <div class="question-images">
            {% for uri in sq.image_data_uris %}
            <img src="{{ uri }}" alt="">
            {% endfor %}
          </div>
          {% endif %}
          {% if sq.answers %}
          <div class="sub-answers-grid">
            {% for ans in sq.answers %}
            <div class="answer-choice"><strong>{{ ans.label }}.</strong>&nbsp;{{ ans.value | e }}</div>
            {% endfor %}
          </div>
          {% elif sq.is_short_answer %}
          <div class="answer-blank">Trả lời: ___________________________________</div>
          {% elif sq.is_essay %}
          <div class="essay-lines">
            {% for _ in range(4) %}<div class="essay-line"></div>{% endfor %}
          </div>
          {% endif %}
        </div>
        {% endfor %}

      {# Non-composite answers #}
      {% elif question.answers %}
      <div class="answers-grid">
        {% for ans in question.answers %}
        <div class="answer-choice"><strong>{{ ans.label }}.</strong>&nbsp;{{ ans.value | e }}</div>
        {% endfor %}
      </div>
      {% elif question.is_short_answer %}
      <div class="answer-blank">Trả lời: ___________________________________</div>
      {% elif question.is_essay %}
      <div class="essay-lines">
        {% for _ in range(5) %}<div class="essay-line"></div>{% endfor %}
      </div>
      {% endif %}

    </div>
  {% endfor %}
</div>
{% endfor %}

<div class="exam-footer">— Hết —</div>

{# ── ANSWER KEY ── #}
{% if include_answer_key %}
<div class="answer-key-page">
  <div class="answer-key-title">Bảng Đáp Án / Answer Key</div>
  {% set ak = namespace(n=0) %}
  {% for section in sections %}
  <div class="answer-key-section">
    <div class="answer-key-section-title">{{ section.name | e }}</div>
    <div class="answer-key-grid">
      {% for question in section.questions %}
        {% set ak.n = ak.n + 1 %}
        {% if question.is_composite %}
          {% for sq in question.sub_questions %}
            {% if sq.correct_label %}
            <div class="answer-key-item">Câu {{ ak.n }}.{{ loop.index }}: <strong>{{ sq.correct_label }}</strong></div>
            {% elif sq.correct_text %}
            <div class="answer-key-item">Câu {{ ak.n }}.{{ loop.index }}: {{ sq.correct_text | e }}</div>
            {% endif %}
          {% endfor %}
        {% elif question.correct_label %}
          <div class="answer-key-item">Câu {{ ak.n }}: <strong>{{ question.correct_label }}</strong></div>
        {% elif question.correct_text %}
          <div class="answer-key-item">Câu {{ ak.n }}: {{ question.correct_text | e }}</div>
        {% endif %}
      {% endfor %}
    </div>
  </div>
  {% endfor %}
</div>
{% endif %}

</body>
</html>
"""


# ---------------------------------------------------------------------------
# Jinja2 environment
# ---------------------------------------------------------------------------

_JINJA_ENV = Environment(undefined=StrictUndefined, autoescape=False)
_TEMPLATE = _JINJA_ENV.from_string(_TEMPLATE_SRC)


# ---------------------------------------------------------------------------
# Pipeline
# ---------------------------------------------------------------------------

class ExamPdfBuildPipelineV2(BasePipeline[ExamPdfBuildInput, bytes]):
    """Pipeline v2: Jinja2 + KaTeX math rendering + Playwright PDF print."""

    def validate(self, payload: ExamPdfBuildInput) -> None:
        if not payload.exam_data:
            raise ValueError("exam_data is required")
        if "sections" not in payload.exam_data:
            raise ValueError("exam_data must contain 'sections'")

    async def process(self, payload: ExamPdfBuildInput) -> bytes:
        exam_data = payload.exam_data
        sections = _prepare_sections(exam_data.get("sections", []), payload.presigned_urls)
        total_questions = sum(len(s["questions"]) for s in sections)

        html_str = _TEMPLATE.render(
            school_name=exam_data.get("school_name") or payload.school_name,
            subject_label=payload.subject_label,
            duration_minutes=payload.duration_minutes,
            exam_code=exam_data.get("exam_test_code", ""),
            total_questions=total_questions,
            sections=sections,
            include_answer_key=payload.include_answer_key,
        )

        return await _html_to_pdf(html_str)


async def _html_to_pdf(html: str) -> bytes:
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        page = await browser.new_page()

        await page.set_content(html, wait_until="networkidle")

        # Wait for KaTeX auto-render to finish
        await page.wait_for_function(
            "() => document.querySelectorAll('.katex').length > 0 || "
            "!document.querySelector('script[src*=\"auto-render\"]')"
        )
        await asyncio.sleep(0.3)

        pdf_bytes = await page.pdf(
            format="A4",
            margin={"top": "2.2cm", "bottom": "2.2cm", "left": "2.5cm", "right": "2.5cm"},
            print_background=True,
        )
        await browser.close()
        return pdf_bytes
