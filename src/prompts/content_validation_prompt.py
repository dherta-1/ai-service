content_validation_prompt = """
You are validating OCR markdown for a single exam page.

Input markdown may contain OCR noise, broken formulas, wrong line breaks, and misplaced options.
Use the provided image as the source of truth and normalize the markdown.

Rules:
1. Keep the same language as the input.
2. Preserve all information from the image, but fix OCR mistakes.
3. Keep math/science expressions in LaTeX when needed. Better nest in $...$ or $$...$$ instead of plain text if it improves readability.
4. For table validating, convert to latex tabular format if it improves readability. Otherwise, keep as-is. Do not add markdown tables or other formats. 
5. Keep image references (e.g., <img ... />) if present in input markdown.
6. Output only clean markdown for this page, no JSON, no explanations.

OCR markdown input:
[RAW TEXT START]
{markdown_content}
[RAW TEXT END]
""".strip()
