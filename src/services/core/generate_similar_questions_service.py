"""Service for generating similar questions using RAG pattern.

RAG Flow:
1. Get base question by ID and extract its vector embedding
2. Perform vector search on QuestionGroups with configured threshold
3. Select k questions (one per group, with lowest variant_existence_count)
4. Inject base question + reference questions into LLM prompt
5. Extract and return LLM-generated questions (no persistence)
"""

from __future__ import annotations

import logging
import re
from typing import Dict, List, Any
from uuid import UUID

from src.repos.question_repo import QuestionRepository
from src.repos.question_group_repo import QuestionGroupRepository
from src.repos.answer_repo import AnswerRepository
from src.prompts.generate_similar_questions import (
    build_generate_similar_questions_prompt,
    extract_generated_questions,
)

logger = logging.getLogger(__name__)


class GenerateSimilarQuestionsService:
    """Generate similar questions using vector search + LLM."""

    def __init__(self, llm_client):
        self._llm = llm_client
        self._question_repo = QuestionRepository()
        self._group_repo = QuestionGroupRepository()
        self._answer_repo = AnswerRepository()

    async def generate_similar_questions(
        self,
        question_id: UUID,
        k: int = 3,
        vector_threshold: float = 0.5,
        num_generate: int = 3,
    ) -> Dict[str, Any]:
        """Generate questions similar to base question using RAG.

        Args:
            question_id: Base question to generate variations for
            k: Number of reference groups to retrieve
            vector_threshold: Cosine similarity threshold for vector search
            num_generate: Number of questions to generate

        Returns:
            {
                base_question: {...},
                generated_questions: [...],
                total_generated: int
            }

        Raises:
            ValueError: If question not found or has no vector embedding
        """
        base_question = self._question_repo.get_by_id(question_id)
        if not base_question:
            raise ValueError(f"Question {question_id} not found")

        if not base_question.vector_embedding.any():
            raise ValueError(
                f"Question {question_id} has no vector embedding for search"
            )

        base_data = self._build_question_dict(base_question)

        candidates = self._group_repo.find_by_metadata(
            subject=base_question.subject,
            topic=base_question.topic,
            difficulty=base_question.difficulty,
        )

        if not candidates:
            logger.warning(
                "No candidate groups found for subject=%s, topic=%s, difficulty=%s",
                base_question.subject,
                base_question.topic,
                base_question.difficulty,
            )
            matched_groups = []
        else:
            matched_groups = self._group_repo.cosine_search(
                candidates=candidates,
                vector=base_question.vector_embedding,
                threshold=vector_threshold,
            )

        reference_questions = self._select_reference_questions(matched_groups, k)
        reference_data = [self._build_question_dict(q) for q in reference_questions]

        prompt = build_generate_similar_questions_prompt(
            base_question=base_data,
            reference_questions=reference_data,
            num_questions=num_generate,
        )

        llm_response = self._llm.generate(prompt)

        try:
            generated_list = extract_generated_questions(llm_response)
        except Exception as e:
            logger.error("Failed to extract generated questions: %s", e)
            raise ValueError(f"Failed to parse LLM response: {e}")

        normalized_questions = [
            self._normalize_generated_question(q) for q in generated_list
        ]

        return {
            "base_question": base_data,
            "generated_questions": normalized_questions,
            "total_generated": len(normalized_questions),
        }

    def _build_question_dict(self, question) -> Dict[str, Any]:
        """Convert Question entity to dictionary with answers."""
        answers = self._answer_repo.get_by_question(question.id)
        answers_list = [{"value": a.value, "is_correct": a.is_correct} for a in answers]

        return {
            "id": str(question.id),
            "question_text": question.question_text,
            "question_type": question.question_type,
            "difficulty": question.difficulty,
            "subject": question.subject,
            "topic": question.topic,
            "answers": answers_list if answers_list else None,
            "image_list": question.image_list,
        }

    def _select_reference_questions(self, matched_groups: List, k: int) -> List:
        """Select one question per group with lowest variant_existence_count.

        Args:
            matched_groups: List of matched QuestionGroup objects
            k: Maximum number of questions to select

        Returns:
            List of selected Question entities
        """
        selected = []
        for group in matched_groups[:k]:
            questions = self._question_repo.get_by_group(group.id)

            if not questions:
                continue

            best_q = min(questions, key=lambda q: q.variant_existence_count)

            if self._has_sufficient_data(best_q):
                selected.append(best_q)

        return selected

    def _has_sufficient_data(self, question) -> bool:
        """Validate that question has sufficient data for reference.

        Args:
            question: Question entity to validate

        Returns:
            True if question has question_text and answers
        """
        if not question.question_text:
            return False

        answers = self._answer_repo.get_by_question(question.id)
        if not answers or len(answers) == 0:
            return False

        return True

    def _normalize_generated_question(self, question: Dict[str, Any]) -> Dict[str, Any]:
        """Normalize and validate generated question, including LaTeX cleanup.

        Args:
            question: Question dict from LLM extraction

        Returns:
            Normalized question dict with validated LaTeX
        """
        normalized = dict(question)

        if "question_text" in normalized and normalized["question_text"]:
            normalized["question_text"] = self._normalize_latex(
                normalized["question_text"]
            )

        if "answers" in normalized and isinstance(normalized["answers"], list):
            normalized["answers"] = [
                self._normalize_answer(a) for a in normalized["answers"]
            ]

        return normalized

    def _normalize_latex(self, text: str) -> str:
        """Normalize LaTeX in text.

        Handles:
        - Escape unescaped backslashes
        - Fix common inline math delimiters
        - Normalize spacing around LaTeX commands
        - Remove orphaned backslashes

        Args:
            text: Text that may contain LaTeX

        Returns:
            Normalized text with valid LaTeX
        """
        if not text:
            return text

        text = str(text)

        # Remove leading/trailing whitespace
        text = text.strip()

        # Fix backslash issues: collapse multiple backslashes to single
        text = re.sub(r'\\{2,}', r'\\', text)

        # Escape unescaped backslashes (preceded by non-escape chars)
        # Look for backslashes that aren't part of LaTeX commands
        text = re.sub(r'(?<!\\)\\(?![\\{}$a-zA-Z])', r'\\', text)

        # Normalize inline math: $...$ should have spaces around it
        text = re.sub(r'\$\s+', r'$', text)
        text = re.sub(r'\s+\$', r'$', text)

        # Fix orphaned backslashes at start/end
        text = re.sub(r'^\\+\s+', '', text)
        text = re.sub(r'\s+\\+$', '', text)

        return text

    def _normalize_answer(self, answer: Dict[str, Any]) -> Dict[str, Any]:
        """Normalize answer dict, including LaTeX in value.

        Args:
            answer: Answer dict with 'value' and 'is_correct'

        Returns:
            Normalized answer dict
        """
        normalized = dict(answer)

        if "value" in normalized and normalized["value"]:
            normalized["value"] = self._normalize_latex(normalized["value"])

        # Ensure is_correct is boolean
        if "is_correct" in normalized:
            normalized["is_correct"] = bool(normalized["is_correct"])

        return normalized
