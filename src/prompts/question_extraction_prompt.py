question_extraction_prompt_template = """
You are extracting questions from a single exam page.

Use BOTH inputs as context:
1) The page image (source of truth).
2) The overlap content (tail of the previous page, if available) to resolve questions spanning page boundaries.
3) The page markdown (already OCR + normalized).

Your task is to return ONLY valid JSON. The output MUST follow the exact schema shown in the example below.
**CRITICAL: Use LaTeX for all mathematical formulas and expressions.**

OUTPUT FORMAT EXAMPLE:
{{
  "questions": [
    {{
      "question_text": "Cho hàm số $f(x) = 2\\cos x + x$.",
      "question_type": "composite",
      "difficulty": "medium",
      "subject": "math",
      "subject_vi": "Toán",
      "topic": "calculus",
      "topic_vi": "Giải tích",
      "answers": null,
      "image_list": [],
      "sub_questions": [
        {{
          "order": 1,
          "sub_question_text": "$f(0)=2$; $f\\left(\\frac{{\\pi}}{{2}}\\right)=\\frac{{\\pi}}{{2}}$",
          "question_type": "true_false",
          "answers": [{{"value": "True", "is_correct": true }}, {{"value": "False", "is_correct": false }}],
          "image_list": []
        }},
        {{
          "order": 2,
          "sub_question_text": "Tính $f'(x)$ và xác định các điểm cực trị của hàm số.",
          "question_type": "short_answer",
          "answers": [{{"value": "$f'(x) = -2\\sin x + 1$; Điểm cực trị tại $x = \\arcsin(\\frac{{1}}{{2}}) + 2k\\pi$ và $x = \\pi - \\arcsin(\\frac{{1}}{{2}}) + 2k\\pi$, với $k \\in \\mathbb{{Z}}$", "is_correct": true }}],
          "image_list": []
        }}
      ]
    }},
    {{
      "question_text": "Tính giá trị của biểu thức $P = \\sqrt{{a^2 + b^2}}$ tại $a=3, b=4$.",
      "question_type": "multiple_choice",
      "difficulty": "easy",
      "subject": "math",
      "subject_vi": "Toán",
      "topic": "algebra",
      "topic_vi": "Đại số",
      "answers": [{{"value": "5", "is_correct": true }}, {{"value": "7", "is_correct": false }}, {{"value": "25", "is_correct": false }}, {{"value": "12", "is_correct": false }}],
      "image_list": [],
      "sub_questions": []
    }},
    {{
      "question_text": "Giải phương trình $x^2 - 4 = 0$.",
      "question_type": "short_answer",
      "difficulty": "easy",
      "subject": "math",
      "subject_vi": "Toán",
      "topic": "algebra",
      "topic_vi": "Đại số",
      "answers": [{{"value": "$x = 2$ or $x = -2$", "is_correct": true }}],
      "image_list": [],
      "sub_questions": []
    }}
  ]
}}

STRICT RULES:
1. Return ONLY valid JSON. No markdown formatting blocks (do not use ```json), no code fences, no explanations.
2. EXTRACT EVERY QUESTION from the `markdown_content`. Do not skip "Phần I", "Phần II", or stop early.
3. Use LaTeX for all math (e.g., $f(x)$, $\\frac{{a}}{{b}}$, $\\sqrt{{x}}$). Use double backslashes for LaTeX commands inside JSON strings (e.g., "\\\\frac").
4. Each main question MUST have exactly these 8 fields: question_text, question_type, difficulty, subject, topic, answers, image_list, sub_questions.
5. question_text: make sure to remove leading question numbers or letters (e.g., "Câu 1.", "a)", etc.) from the question_text. For sub-questions, also strip leading letters/numbers from sub_question_text. For any tables that are in html, still keep it and normalize for correctness (e.g., fix broken tags, ensure it's valid html)
6. question_type: MUST be one of: {question_types}.
7. difficulty: MUST be one of: {difficulty_levels}.
8. subject: MUST be one of: {subjects}. Also return its vietnamese name in subject_vi. If unknown, set subject_vi to null.
9. topic: must be in snake_case and as specific as possible (e.g., "calculus", "algebra", "physics_mechanics", etc.). Also return its vietnamese name in topic_vi. If unknown, set topic_vi to null.
10. answers:
    - For multiple_choice, selection, true_false: return JSON array of {{"value": "...", "is_correct": true|false}}. Strip leading option letters (A., B., etc.). Mark exactly ONE answer as is_correct: true.
    - For short_answer, essay: return JSON array with ONE item {{"value": "...", "is_correct": true}} representing the correct answer, or null if unknown.
    - For composite: answers must be null (use sub_questions instead).
11. image_list: JSON array of image/table references tied to this question, or [] if none.
12. Composite/Sub-questions: For shared stems, use "composite" type. Put the shared context in `question_text`. Sub-questions MUST have: {{"sub_question_text": "...", "question_type": "...", "answers": [...|null], "image_list": []}}.
13. If overlap_content is provided, use it for context only. Do NOT re-extract questions solely from it.

Current page markdown:
[START OVERLAP CONTENT]
{overlap_section}
[END OVERLAP CONTENT]
[START PAGE MARKDOWN]
{markdown_content}
[END PAGE MARKDOWN]
""".strip()
