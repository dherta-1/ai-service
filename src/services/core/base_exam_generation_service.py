"""Base Exam Generation Service - Core Generation Logic.

Pure generation logic for base exam instances.
All lifecycle operations (template CRUD, status management, etc.) are in ExamService.

Exports:
  - generate_base_exam — core generation algorithm
  - _create_exam_instance — internal helper
  - Private methods for variant selection and shuffling
"""

from __future__ import annotations

import json
import logging
import random
from typing import List, Optional
from uuid import UUID

from src.calculations.diversity_penalty import select_groups_greedy
from src.dtos.exam.req import SectionConfig
from src.entities.exam_instance import ExamInstance
from src.entities.question import Question
from src.entities.question_group import QuestionGroup
from src.repos.answer_repo import AnswerRepository
from src.repos.exam_instance_repo import ExamInstanceRepository
from src.repos.exam_template_repo import ExamTemplateRepository
from src.repos.exam_test_section_repo import ExamTestSectionRepository
from src.repos.question_exam_test_repo import QuestionExamTestRepository
from src.repos.question_group_repo import QuestionGroupRepository
from src.repos.question_repo import QuestionRepository
from src.shared.constants.exam import ExamInstanceStatus
from src.shared.helpers.exam_generation_helpers import generate_exam_code, increment_exam_counts

logger = logging.getLogger(__name__)

_DIFFICULTY_FALLBACKS = {
    "easy": ["medium", "hard"],
    "medium": ["easy", "hard"],
    "hard": ["medium", "easy"],
}


class BaseExamGenerationService:
    """Base exam generation - pure algorithmic core.

    Focuses on exam creation from section configs. All template and lifecycle
    operations are delegated to ExamService.
    """

    def __init__(self, llm_client=None):
        self._template_repo = ExamTemplateRepository()
        self._instance_repo = ExamInstanceRepository()
        self._section_repo = ExamTestSectionRepository()
        self._qet_repo = QuestionExamTestRepository()
        self._group_repo = QuestionGroupRepository()
        self._question_repo = QuestionRepository()
        self._answer_repo = AnswerRepository()
        self._llm_client = llm_client


    # ------------------------------------------------------------------
    # Base exam generation (core algorithm)
    # ------------------------------------------------------------------

    def generate_base_exam(
        self,
        sections: List[SectionConfig],
        template_id: Optional[UUID] = None,
        subject: Optional[str] = None,
        created_by_id: Optional[UUID] = None,
    ) -> ExamInstance:
        """Generate a base ExamInstance.

        Mode 1 (regenerate): template_id given — load template, override sections if provided
        Mode 2 (one-off):    template_id=None — use sections directly, subject required
        """
        final_sections = self._resolve_sections(sections, template_id, subject)
        exam = self._create_exam_instance(
            template_id=template_id,
            sections=final_sections,
            is_base=True,
            created_by_id=created_by_id,
        )
        logger.info("Generated base exam %s with %d sections", exam.id, len(final_sections))
        return exam

    def _resolve_sections(
        self,
        sections: List[SectionConfig],
        template_id: Optional[UUID],
        subject: Optional[str],
    ) -> List[SectionConfig]:
        if template_id:
            template = self._template_repo.get_by_id(template_id)
            if not template:
                raise ValueError(f"Template {template_id} not found")
            if not sections and template.generation_config:
                raw = json.loads(template.generation_config)
                sections = [SectionConfig(**s) for s in raw]
        else:
            if not subject:
                raise ValueError("subject is required when template_id is not provided")

        if not sections:
            raise ValueError("No sections provided and template has no default config")

        return sections

    def _create_exam_instance(
        self,
        template_id: Optional[UUID],
        sections: List[SectionConfig],
        is_base: bool,
        parent_exam_id: Optional[UUID] = None,
        created_by_id: Optional[UUID] = None,
    ) -> ExamInstance:
        exam = self._instance_repo.create(
            exam_template=template_id,
            parent_exam_instance=parent_exam_id,
            exam_test_code=generate_exam_code(),
            is_base=is_base,
            status=ExamInstanceStatus.PENDING,
            created_by_id=created_by_id,
        )

        all_group_ids: List[UUID] = []
        all_question_ids: List[UUID] = []

        for order_idx, section in enumerate(sections):
            sec_obj = self._section_repo.create(
                exam_instance=exam.id,
                name=section.name,
                order_index=order_idx,
            )

            candidates = self._retrieve_candidate_groups(section)
            if not candidates:
                logger.warning(
                    "No candidate groups for section '%s' (%s/%s/%s)",
                    section.name, section.subject, section.topic, section.difficulty,
                )
                continue

            query_vec = self._embed_custom_text(section.custom_text)
            selected = select_groups_greedy(
                candidates=candidates,
                top_k=section.top_k,
                random_level=section.random_level,
                query_embedding=query_vec,
            )

            for q_order, group in enumerate(selected):
                variant = self._pick_variant(group, section.question_type)
                if not variant:
                    continue

                answer_order = self._shuffle_answers(variant)
                self._qet_repo.create(
                    question_group=group.id,
                    question_id=str(variant.id),
                    exam_test_section=sec_obj.id,
                    order_count=q_order,
                    answer_order=json.dumps(answer_order),
                )
                all_group_ids.append(group.id)
                all_question_ids.append(variant.id)

        increment_exam_counts(all_group_ids, all_question_ids)
        return exam


    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _retrieve_candidate_groups(self, section: SectionConfig) -> List[QuestionGroup]:
        candidates = self._group_repo.find_by_metadata(
            section.subject, section.topic, section.difficulty
        )

        if not candidates:
            for fallback_diff in _DIFFICULTY_FALLBACKS.get(section.difficulty, []):
                candidates = self._group_repo.find_by_metadata(
                    section.subject, section.topic, fallback_diff
                )
                if candidates:
                    logger.info(
                        "Fell back to difficulty '%s' for section '%s'",
                        fallback_diff, section.name,
                    )
                    break

        if not candidates:
            return []

        # Filter by question_type if specified
        if section.question_type:
            filtered = []
            for group in candidates:
                # Get any question from this group to check its type
                questions = self._question_repo.get_by_group(group.id)
                if questions and any(q.question_type == section.question_type for q in questions):
                    filtered.append(group)
            candidates = filtered

        if not candidates:
            return []

        # If custom_text: vector-rank via cosine (no threshold — just sort)
        if section.custom_text and self._llm_client:
            query_vec = self._embed_custom_text(section.custom_text)
            if query_vec:
                candidates = self._group_repo.cosine_search(candidates, query_vec, threshold=0.0)
                return candidates[: 5 * section.top_k]

        # No custom_text: random sample pool of 5*top_k to avoid full-scan scoring
        k = min(len(candidates), 5 * section.top_k)
        return random.sample(candidates, k)

    def _embed_custom_text(self, text: Optional[str]) -> Optional[List]:
        if not text or not self._llm_client:
            return None
        try:
            return self._llm_client.embed(text)
        except Exception as exc:
            logger.warning("Failed to embed custom_text: %s", exc)
            return None

    def _pick_variant(
        self, group: QuestionGroup, question_type: Optional[str] = None, rng: random.Random = None
    ) -> Optional[Question]:
        variants = list(
            Question.select().where(
                (Question.questions_group == group.id)
                & (Question.parent_question.is_null())
            )
        )
        if not variants:
            return None

        if question_type:
            variants = [v for v in variants if v.question_type == question_type]
            if not variants:
                return None

        weights = [1.0 / (v.variant_existence_count + 1) for v in variants]
        total = sum(weights)
        probs = [w / total for w in weights]
        _rng = rng or random
        return _rng.choices(variants, weights=probs, k=1)[0]

    def _shuffle_answers(self, question: Question, rng: random.Random = None) -> List[int]:
        answers = self._answer_repo.get_by_question(question.id)
        indices = list(range(len(answers)))
        _rng = rng or random
        _rng.shuffle(indices)
        return indices

