question_extraction_prompt = """
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
      "question_text": "Câu 1. Cho hàm số $f(x) = 2\\cos x + x$.",
      "question_type": "composite",
      "difficulty": "medium",
      "subject": "math",
      "topic": "calculus",
      "answers": null,
      "correct_answer": null,
      "image_list": [],
      "sub_questions": [
        {{
          "sub_question_text": "a) $f(0)=2$; $f\\left(\\frac{{\\pi}}{{2}}\\right)=\\frac{{\\pi}}{{2}}$",
          "question_type": "true_false",
          "answers": ["True", "False"],
          "correct_answer": "True"
        }}
      ]
    }},
    {{
      "question_text": "Câu 2. Tính giá trị của biểu thức $P = \\sqrt{{a^2 + b^2}}$ tại $a=3, b=4$.",
      "question_type": "multiple_choice",
      "difficulty": "easy",
      "subject": "math",
      "topic": "algebra",
      "answers": ["5", "7", "25", "12"],
      "correct_answer": "5",
      "image_list": [],
      "sub_questions": []
    }}
  ]
}}

STRICT RULES:
1. Return ONLY valid JSON. No markdown formatting blocks (do not use ```json), no code fences, no explanations.
2. EXTRACT EVERY QUESTION from the `markdown_content`. Do not skip "Phần I", "Phần II", or stop early. 
3. Use LaTeX for all math (e.g., $f(x)$, $\\frac{{a}}{{b}}$, $\\sqrt{{x}}$). Use double backslashes for LaTeX commands inside JSON strings (e.g., "\\\\frac").
4. Each main question MUST have exactly these 9 fields: question_text, question_type, difficulty, subject, topic, answers, correct_answer, image_list, sub_questions.
5. question_text: make sure to remove leading question numbers or letters (e.g., "Câu 1.", "a)", etc.) from the question_text. For sub-questions, also strip leading letters/numbers from sub_question_text.
6. question_type: MUST be one of: "multiple_choice", "true_false", "short_answer", "essay", or "composite".
7. answers: For multiple_choice, return a standard JSON array of strings. Strip leading option letters (A., B., etc.). For true_false, return ["True", "False"]. For others, must be null.
8. correct_answer: The correct answer string WITHOUT the option letter, or null if unknown.
9. image_list: JSON array of image/table references tied to this question, or [] if none.
10. Composite/Sub-questions: For shared stems, use "composite" type. Put the shared context in `question_text`. Sub-questions MUST have: {{"sub_question_text": "...", "question_type": "...", "answers": [...|null], "correct_answer": "...|null"}}.
11. If overlap_content is provided, use it for context only. Do NOT re-extract questions solely from it.

Current page markdown:
{overlap_section}

{markdown_content}
""".strip()
