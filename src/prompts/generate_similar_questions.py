"""Prompt template for generating similar questions via RAG pattern."""

from typing import List, Dict


def build_generate_similar_questions_prompt(
    base_question: Dict,
    reference_questions: List[Dict],
    num_questions: int = 3,
) -> str:
    """Build a prompt for generating similar questions based on a base question and references.

    Args:
        base_question: The question to generate variations for
        reference_questions: Questions with similar semantic meaning (from vector search)
        num_questions: Number of questions to generate

    Returns:
        Formatted prompt string
    """
    base_text = base_question.get("question_text", "")
    base_type = base_question.get("question_type", "")
    base_difficulty = base_question.get("difficulty", "")
    base_subject = base_question.get("subject", "")
    base_topic = base_question.get("topic", "")
    base_answers = base_question.get("answers", [])

    reference_section = ""
    if reference_questions:
        reference_section = "\n## Reference Questions (Similar semantic meaning):\n"
        for i, ref in enumerate(reference_questions, 1):
            reference_section += f"\nReference {i}:\n"
            reference_section += f"  Question: {ref.get('question_text', '')}\n"
            reference_section += f"  Type: {ref.get('question_type', '')}\n"
            if ref.get("answers"):
                reference_section += f"  Answers: {ref.get('answers')}\n"

    prompt = f"""You are an expert educator tasked with generating new exam questions that are semantically similar to a base question.

## Base Question (to generate variations for):
Question: {base_text}
Type: {base_type}
Difficulty: {base_difficulty}
Subject: {base_subject}
Topic: {base_topic}
Answers: {base_answers}
{reference_section}

## Task:
Generate exactly {num_questions} new questions that:
1. Share the same semantic meaning and learning objectives as the base question
2. Have the same question type ({base_type})
3. Have similar difficulty level ({base_difficulty})
4. Fall under the same subject ({base_subject}) and topic ({base_topic})
5. Use different wording and context than the base question and all references
6. Are distinct from each other

## Output Format:
Return a JSON array with exactly {num_questions} objects, each with the following structure:
{{
  "question_text": "...",
  "question_type": "{base_type}",
  "difficulty": "{base_difficulty}",
  "subject": "{base_subject}",
  "topic": "{base_topic}",
  "answers": [
    {{"value": "...", "is_correct": true}},
    {{"value": "...", "is_correct": false}}
  ]
}}

IMPORTANT:
- For True/False questions: Include both True and False options, mark exactly one as correct
- For Multiple Choice: Include 3-4 options, mark exactly one as correct
- For Selection: Include multiple correct answers
- For Short Answer/Essay: Include the expected answer(s) with is_correct: true
- Ensure all answers follow the exact format: [{{"value": "...", "is_correct": boolean}}]
- Return ONLY the JSON array, no additional text

Generate the {num_questions} questions now:"""

    return prompt


def extract_generated_questions(response_text: str) -> List[Dict]:
    """Extract and parse generated questions from LLM response.

    Args:
        response_text: Raw LLM response text

    Returns:
        List of parsed question dictionaries
    """
    import json
    import re

    response_text = response_text.strip()

    json_match = re.search(r"\[[\s\S]*\]", response_text)
    if not json_match:
        raise ValueError("No JSON array found in LLM response")

    json_str = json_match.group(0)
    questions = json.loads(json_str)

    if not isinstance(questions, list):
        raise ValueError("Expected JSON array in response")

    return questions
