"""Exam generation helper functions - shared utilities for both base and variant generation."""

import random
import string
from typing import List
from uuid import UUID

from src.entities.question import Question
from src.entities.question_group import QuestionGroup


def generate_exam_code() -> str:
    """Generate a unique exam code (EXAM-XXXXXXXX)."""
    chars = string.ascii_uppercase + string.digits
    suffix = "".join(random.choices(chars, k=8))
    return f"EXAM-{suffix}"


def increment_exam_counts(group_ids: List[UUID], question_ids: List[UUID]) -> None:
    """Increment existence counts for question groups and questions after exam creation."""
    if group_ids:
        QuestionGroup.update(
            existence_count=QuestionGroup.existence_count + 1
        ).where(QuestionGroup.id.in_(group_ids)).execute()

    if question_ids:
        Question.update(
            variant_existence_count=Question.variant_existence_count + 1
        ).where(Question.id.in_(question_ids)).execute()


def shuffle_answer_indices(question: Question, answer_repo) -> List[int]:
    """Shuffle answer indices for a question."""
    answers = answer_repo.get_by_question(question.id)
    indices = list(range(len(answers)))
    random.shuffle(indices)
    return indices
