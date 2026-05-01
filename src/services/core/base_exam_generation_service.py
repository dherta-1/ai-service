"""Base Exam Generation Service.

Handles:
  - save_template      — create or update ExamTemplate with section defaults
  - generate_base_exam — create a base ExamInstance from section configs
  - update_exam_status — accept / reject an exam after review
  - replace_question   — swap a variant within the same QuestionGroup
"""

from __future__ import annotations

import json
import logging
import random
import string
from typing import List, Optional
from uuid import UUID

from src.calculations.diversity_penalty import select_groups_greedy
from src.dtos.exam.req import SectionConfig
from src.entities.exam_instance import ExamInstance
from src.entities.exam_template import ExamTemplate
from src.entities.question import Question
from src.entities.question_exam_test import QuestionExamTest
from src.entities.question_group import QuestionGroup
from src.repos.answer_repo import AnswerRepository
from src.repos.exam_instance_repo import ExamInstanceRepository
from src.repos.exam_template_repo import ExamTemplateRepository
from src.repos.exam_test_section_repo import ExamTestSectionRepository
from src.repos.question_exam_test_repo import QuestionExamTestRepository
from src.repos.question_group_repo import QuestionGroupRepository
from src.repos.question_repo import QuestionRepository
from src.shared.constants.exam import ExamInstanceStatus

logger = logging.getLogger(__name__)

_DIFFICULTY_FALLBACKS = {
    "easy": ["medium", "hard"],
    "medium": ["easy", "hard"],
    "hard": ["medium", "easy"],
}


class BaseExamGenerationService:
    """Generate and manage base (is_base=True) exam instances."""

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
    # Template management
    # ------------------------------------------------------------------

    def save_template(
        self,
        name: str,
        subject: str,
        generation_config: Optional[List[SectionConfig]] = None,
        template_id: Optional[UUID] = None,
    ) -> ExamTemplate:
        """Create or update an ExamTemplate.

        Args:
            name:              human-readable template name
            subject:           top-level subject code (e.g. "math")
            generation_config: default section configs stored as JSON
            template_id:       if given, update that template; else create new

        Returns:
            Saved ExamTemplate instance
        """
        config_json = (
            json.dumps([s.model_dump() for s in generation_config])
            if generation_config
            else None
        )

        if template_id:
            template = self._template_repo.get_by_id(template_id)
            if not template:
                raise ValueError(f"Template {template_id} not found")
            template.name = name
            template.subject = subject
            template.generation_config = config_json
            template.save()
            return template

        return self._template_repo.create(
            name=name,
            subject=subject,
            generation_config=config_json,
        )

    def get_template(self, template_id: UUID) -> Optional[ExamTemplate]:
        return self._template_repo.get_by_id(template_id)

    def list_templates(self, subject: Optional[str] = None) -> List[ExamTemplate]:
        if subject:
            return self._template_repo.get_by_subject(subject)
        return self._template_repo.get_all()

    # ------------------------------------------------------------------
    # Base exam generation
    # ------------------------------------------------------------------

    def generate_base_exam(
        self,
        sections: List[SectionConfig],
        template_id: Optional[UUID] = None,
        subject: Optional[str] = None,
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
    ) -> ExamInstance:
        exam = self._instance_repo.create(
            exam_template=template_id,
            parent_exam_instance=parent_exam_id,
            exam_test_code=self._generate_code(),
            is_base=is_base,
            status=ExamInstanceStatus.PENDING,
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
                variant = self._pick_variant(group)
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

        self._increment_counts(all_group_ids, all_question_ids)
        return exam

    # ------------------------------------------------------------------
    # Status management
    # ------------------------------------------------------------------

    def update_exam_status(self, exam_id: UUID, status: int) -> ExamInstance:
        """Set exam status. 0=pending, 1=accepted, 2=rejected."""
        if status not in (ExamInstanceStatus.PENDING, ExamInstanceStatus.ACCEPTED, ExamInstanceStatus.REJECTED):
            raise ValueError(f"Invalid status value: {status}")

        exam = self._instance_repo.get_by_id(exam_id)
        if not exam:
            raise ValueError(f"Exam instance {exam_id} not found")

        self._instance_repo.update_status(exam_id, status)
        exam.status = status
        return exam

    # ------------------------------------------------------------------
    # Question replacement (user review)
    # ------------------------------------------------------------------

    def replace_question(
        self,
        exam_instance_id: UUID,
        qet_id: UUID,
        new_question_id: UUID,
    ) -> QuestionExamTest:
        """Replace a question variant within the same QuestionGroup."""
        qet = self._qet_repo.get_by_id(qet_id)
        if not qet:
            raise ValueError(f"QuestionExamTest {qet_id} not found")

        section = self._section_repo.get_by_id(qet.exam_test_section_id)
        if str(section.exam_instance_id) != str(exam_instance_id):
            raise ValueError(f"QuestionExamTest {qet_id} does not belong to exam {exam_instance_id}")

        new_question = self._question_repo.get_by_id(new_question_id)
        if not new_question:
            raise ValueError(f"Question {new_question_id} not found")

        if str(new_question.questions_group_id) != str(qet.question_group_id):
            raise ValueError(
                f"Question {new_question_id} is not in group {qet.question_group_id}"
            )

        qet.question_id = str(new_question_id)
        qet.answer_order = json.dumps(self._shuffle_answers(new_question))
        qet.save()
        return qet

    # ------------------------------------------------------------------
    # Read helpers
    # ------------------------------------------------------------------

    def get_exam_instance(self, exam_id: UUID) -> Optional[ExamInstance]:
        return self._instance_repo.get_by_id(exam_id)

    def get_exam_versions(self, base_exam_id: UUID) -> List[ExamInstance]:
        return self._instance_repo.get_versions_of(base_exam_id)

    def get_base_instances(self, template_id: UUID) -> List[ExamInstance]:
        return self._instance_repo.get_base_instances(template_id)

    def build_exam_response_data(self, exam: ExamInstance) -> dict:
        """Assemble full exam data dict (sections + enriched questions)."""
        sections_data = []
        total_questions = 0

        sections = self._section_repo.get_by_exam_instance(exam.id)
        for sec in sections:
            qets = self._qet_repo.get_by_section(sec.id)
            questions_data = []

            for qet in qets:
                question = self._question_repo.get_by_id(UUID(qet.question_id))
                if not question:
                    continue

                answers = self._answer_repo.get_by_question(question.id)
                sub_questions = self._question_repo.get_sub_questions(question.id)

                answer_order = None
                if qet.answer_order:
                    try:
                        answer_order = json.loads(qet.answer_order)
                    except (ValueError, TypeError):
                        answer_order = None

                questions_data.append({
                    "question_exam_test_id": str(qet.id),
                    "question_id": str(question.id),
                    "question_group_id": str(qet.question_group_id),
                    "order_count": qet.order_count,
                    "answer_order": answer_order,
                    "question_text": question.question_text,
                    "question_type": question.question_type,
                    "difficulty": question.difficulty,
                    "image_list": question.image_list,
                    "answers": [
                        {"id": str(a.id), "value": a.value, "is_correct": a.is_correct}
                        for a in answers
                    ],
                    "sub_questions": [
                        {
                            "question_exam_test_id": str(qet.id),
                            "question_id": str(sq.id),
                            "question_group_id": str(qet.question_group_id),
                            "order_count": sq.sub_question_order or 0,
                            "answer_order": None,
                            "question_text": sq.question_text,
                            "question_type": sq.question_type,
                            "difficulty": None,
                            "image_list": sq.image_list,
                            "answers": [
                                {"id": str(a.id), "value": a.value, "is_correct": a.is_correct}
                                for a in self._answer_repo.get_by_question(sq.id)
                            ],
                            "sub_questions": None,
                        }
                        for sq in sub_questions
                    ] or None,
                })
                total_questions += 1

            sections_data.append({
                "id": str(sec.id),
                "name": sec.name,
                "order_index": sec.order_index,
                "questions": questions_data,
            })

        return {
            "id": str(exam.id),
            "exam_test_code": exam.exam_test_code,
            "is_base": exam.is_base,
            "is_exported": exam.is_exported,
            "status": exam.status,
            "template_id": str(exam.exam_template_id) if exam.exam_template_id else None,
            "parent_exam_instance_id": (
                str(exam.parent_exam_instance_id) if exam.parent_exam_instance_id else None
            ),
            "sections": sections_data,
            "created_at": exam.created_at.isoformat(),
            "updated_at": exam.updated_at.isoformat(),
            "_total_questions": total_questions,
        }

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
        self, group: QuestionGroup, rng: random.Random = None
    ) -> Optional[Question]:
        variants = list(
            Question.select().where(
                (Question.questions_group == group.id)
                & (Question.parent_question.is_null())
            )
        )
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

    def _increment_counts(
        self, group_ids: List[UUID], question_ids: List[UUID]
    ) -> None:
        if group_ids:
            QuestionGroup.update(
                existence_count=QuestionGroup.existence_count + 1
            ).where(QuestionGroup.id.in_(group_ids)).execute()

        if question_ids:
            Question.update(
                variant_existence_count=Question.variant_existence_count + 1
            ).where(Question.id.in_(question_ids)).execute()

    @staticmethod
    def _generate_code() -> str:
        chars = string.ascii_uppercase + string.digits
        suffix = "".join(random.choices(chars, k=8))
        return f"EXAM-{suffix}"
