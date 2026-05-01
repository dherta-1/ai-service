"""Variant Exam Generation Service - Core Generation Logic.

Pure generation logic for variant exam instances.
All lifecycle operations are in ExamService.

Exports:
  - generate_versions — core variant generation algorithm
"""

from __future__ import annotations

import json
import logging
from random import Random
from typing import List
from uuid import UUID, uuid4

from src.entities.exam_instance import ExamInstance
from src.entities.exam_test_section import ExamTestSection
from src.entities.question import Question
from src.repos.answer_repo import AnswerRepository
from src.repos.exam_instance_repo import ExamInstanceRepository
from src.repos.exam_test_section_repo import ExamTestSectionRepository
from src.repos.question_exam_test_repo import QuestionExamTestRepository
from src.repos.question_repo import QuestionRepository
from src.shared.constants.exam import ExamInstanceStatus
from src.shared.helpers.exam_generation_helpers import generate_exam_code, increment_exam_counts

logger = logging.getLogger(__name__)


class VariantExamGenerationService:
    """Variant exam generation - pure algorithmic core.

    Focuses on generating exam variants from an accepted base exam.
    All lifecycle and template operations are in ExamService.
    Uses seed-based RNG so each version is reproducible given its seed.
    """

    def __init__(self, llm_client=None):
        self._instance_repo = ExamInstanceRepository()
        self._section_repo = ExamTestSectionRepository()
        self._qet_repo = QuestionExamTestRepository()
        self._question_repo = QuestionRepository()
        self._answer_repo = AnswerRepository()

    def generate_versions(
        self,
        base_exam_id: UUID,
        num_versions: int,
    ) -> List[ExamInstance]:
        """Generate num_versions version exams from an accepted base exam.

        Args:
            base_exam_id: must be is_base=True and status=ACCEPTED
            num_versions: 1–10

        Raises:
            ValueError: if base is not found, not accepted, or not a base exam
        """
        base = self._instance_repo.get_by_id(base_exam_id)
        if not base:
            raise ValueError(f"Exam instance {base_exam_id} not found")
        if not base.is_base:
            raise ValueError(f"Exam {base_exam_id} is not a base exam")
        if base.status != ExamInstanceStatus.ACCEPTED:
            raise ValueError(
                f"Base exam must be ACCEPTED to generate versions (current status: {base.status})"
            )

        base_sections = self._section_repo.get_by_exam_instance(base.id)
        if not base_sections:
            raise ValueError(f"Base exam {base_exam_id} has no sections")

        versions = []
        for i in range(num_versions):
            seed = str(uuid4())
            version = self._create_version(base, base_sections, seed)
            versions.append(version)
            logger.info("Created version %d/%d → exam %s", i + 1, num_versions, version.id)

        return versions

    def _create_version(
        self,
        base_exam: ExamInstance,
        base_sections: List[ExamTestSection],
        seed: str,
    ) -> ExamInstance:
        version = self._instance_repo.create(
            exam_template=base_exam.exam_template_id,
            parent_exam_instance=base_exam.id,
            exam_test_code=generate_exam_code(),
            is_base=False,
            status=ExamInstanceStatus.PENDING,
            created_by_id=base_exam.created_by_id,
        )

        all_group_ids: List[UUID] = []
        all_question_ids: List[UUID] = []

        for section in base_sections:
            version_section = self._section_repo.create(
                exam_instance=version.id,
                name=section.name,
                order_index=section.order_index,
            )

            base_qets = self._qet_repo.get_by_section(section.id)

            for q_order, base_qet in enumerate(base_qets):
                group_id = UUID(str(base_qet.question_group_id))

                group_rng = Random(seed + str(group_id))
                variant = self._pick_variant_for_group(group_id, rng=group_rng)

                if not variant:
                    logger.warning("No variant found for group %s in version", group_id)
                    continue

                answer_rng = Random(seed + str(variant.id))
                answers = self._answer_repo.get_by_question(variant.id)
                indices = list(range(len(answers)))
                answer_rng.shuffle(indices)

                self._qet_repo.create(
                    question_group=group_id,
                    question_id=str(variant.id),
                    exam_test_section=version_section.id,
                    order_count=q_order,
                    answer_order=json.dumps(indices),
                )

                all_group_ids.append(group_id)
                all_question_ids.append(variant.id)

        increment_exam_counts(all_group_ids, all_question_ids)
        return version

    def _pick_variant_for_group(
        self, group_id: UUID, rng: Random
    ) -> Question | None:
        variants = list(
            Question.select().where(
                (Question.questions_group == group_id)
                & (Question.parent_question.is_null())
            )
        )
        if not variants:
            return None

        weights = [1.0 / (v.variant_existence_count + 1) for v in variants]
        total = sum(weights)
        probs = [w / total for w in weights]
        return rng.choices(variants, weights=probs, k=1)[0]
