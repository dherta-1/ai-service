question_extraction_prompt = """
You are extracting questions from a single exam page.

Use BOTH inputs as context:
1) The page image (source of truth).
2) The page markdown (already OCR + normalized).

Your task is to return ONLY valid JSON. The output MUST be valid JSON.

Output format (use this exact structure):
{"questions": [{"question_text": "...", "question_type": "multiple_choice|true_false|short_answer|essay", "difficulty": "easy|medium|hard|null", "subject": "math|science|history|literature|null", "topic": "...|null", "answers": "...|null", "correct_answer": "...|null", "image_list": [...]}]}

STRICT RULES:
1. Return ONLY valid JSON. No markdown, no code fences, no explanations.
2. If no questions found, return: {"questions": []}
3. Each question MUST have all 8 fields (question_text, question_type, difficulty, subject, topic, answers, correct_answer, image_list).
4. question_text: The full question text. If it depends on an image/table/chart, include that context in the text.
5. question_type: MUST be one of: "multiple_choice", "true_false", "short_answer", "essay"
6. difficulty: MUST be one of: "easy", "medium", "hard", or null
7. subject: MUST be one of: "math", "science", "history", "literature", or null
8. topic: null or a string (e.g., "algebra", "biology", etc.)
9. answers: For multiple_choice, return JSON array like ["A. Option 1", "B. Option 2"]. For true_false, return ["True", "False"]. For short_answer/essay, must be null.
10. correct_answer: The correct answer string, or null if unknown.
11. image_list: JSON array of image/table references tied to this question (from <img> tags or visible regions), or [] if none.

Page markdown:
{markdown_content}
""".strip()
