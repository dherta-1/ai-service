content_validation_prompt = """
You are validating OCR markdown for a single exam page.

Input markdown may contain OCR noise, broken formulas, wrong line breaks, and misplaced options.
Use the provided image as the source of truth and normalize the markdown.

Rules:
1. Keep the same language as the input.
2. Preserve all information from the image, but fix OCR mistakes.
3. Keep math/science expressions in LaTeX when needed.
4. Keep image references (e.g., <img ... />) if present in input markdown.
5. Output only clean markdown for this page, no JSON, no explanations.

OCR markdown input:
{markdown_content}
""".strip()
