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
import time
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
from src.shared.helpers.exam_generation_helpers import (
    generate_exam_code,
    increment_exam_counts,
)

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
        logger.info(
            "Generated base exam %s with %d sections", exam.id, len(final_sections)
        )
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

            # Check if skip_group_filtering is enabled
            if section.skip_group_filtering:
                questions = self._pick_questions_directly(section)
                if not questions:
                    logger.warning(
                        "No questions found for section '%s' with direct picking",
                        section.name,
                    )
                    continue

                q_order = 0
                for question in questions:
                    group = self._group_repo.get_by_id(question.questions_group)
                    answer_order = self._shuffle_answers(question)
                    self._qet_repo.create(
                        question_group=question.questions_group,
                        question_id=str(question.id),
                        exam_test_section=sec_obj.id,
                        order_count=q_order,
                        answer_order=json.dumps(answer_order),
                    )
                    all_group_ids.append(question.questions_group)
                    all_question_ids.append(question.id)
                    q_order += 1
            else:
                # Original group-based filtering
                candidates = self._retrieve_candidate_groups(section)
                if not candidates:
                    logger.warning(
                        "No candidate groups for section '%s' (%s/%s/%s)",
                        section.name,
                        section.subject,
                        section.topic,
                        section.difficulty,
                    )
                    continue

                query_vec = self._embed_custom_text(section.custom_text)

                # Rank all candidate groups by diversity + semantic score
                ranked = select_groups_greedy(
                    candidates=candidates,
                    top_k=len(candidates),  # rank all, distribute slots next
                    random_level=section.random_level,
                    query_embedding=query_vec,
                )

                # Distribute top_k slots across ranked groups (flexible distribution)
                slot_map = self._distribute_slots(ranked, section.top_k)

                q_order = 0
                for group in ranked:
                    count = slot_map.get(group, 0)
                    if count <= 0:
                        continue

                    questions = self._pick_variants(group, count, section.question_type)
                    for question in questions:
                        answer_order = self._shuffle_answers(question)
                        self._qet_repo.create(
                            question_group=group.id,
                            question_id=str(question.id),
                            exam_test_section=sec_obj.id,
                            order_count=q_order,
                            answer_order=json.dumps(answer_order),
                        )
                        all_group_ids.append(group.id)
                        all_question_ids.append(question.id)
                        q_order += 1

        increment_exam_counts(all_group_ids, all_question_ids)
        return exam

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _pick_questions_directly(self, section: SectionConfig) -> List[Question]:
        """Pick questions directly without group filtering.

        Retrieves all eligible questions matching criteria (subject, topic, difficulty,
        question_type) then uses weighted sampling without replacement to select top_k.

        If custom_text is provided, applies cosine similarity ranking before sampling.
        Weight is inversely proportional to variant_existence_count.
        """
        topics = section.topic if isinstance(section.topic, list) else [section.topic]
        types_to_match = (
            section.question_type
            if isinstance(section.question_type, list)
            else [section.question_type]
        ) if section.question_type else None

        # Get all eligible questions with difficulty fallback
        questions = self._question_repo.get_by_criteria_with_fallback(
            subject=section.subject,
            topics=topics,
            difficulty=section.difficulty,
            fallback_difficulties=_DIFFICULTY_FALLBACKS.get(section.difficulty),
            question_types=types_to_match,
        )

        if not questions:
            logger.warning(
                "No questions found for section '%s' (subject=%s, topics=%s, difficulty=%s)",
                section.name,
                section.subject,
                topics,
                section.difficulty,
            )
            return []

        # Apply cosine search ranking if custom_text provided
        if section.custom_text and self._llm_client:
            query_vec = self._embed_custom_text(section.custom_text)
            if query_vec is not None:
                # Rank questions by cosine similarity to custom_text
                questions = self._rank_questions_by_similarity(questions, query_vec)
                # Take top 5*top_k to avoid full-scan, then sample from this pool
                questions = questions[: 5 * section.top_k]
                logger.info(
                    "Ranked %d questions by semantic similarity for section '%s'",
                    len(questions),
                    section.name,
                )

        # Weighted sampling without replacement
        selected = []
        pool = list(questions)
        k = min(section.top_k, len(pool))

        for _ in range(k):
            weights = [1.0 / (q.variant_existence_count + 1) for q in pool]
            total = sum(weights)
            probs = [w / total for w in weights]
            idx = random.choices(range(len(pool)), weights=probs, k=1)[0]
            selected.append(pool[idx])
            pool.pop(idx)

        logger.info(
            "Picked %d questions directly for section '%s'",
            len(selected),
            section.name,
        )
        return selected

    def _retrieve_candidate_groups(self, section: SectionConfig) -> List[QuestionGroup]:
        topics = section.topic if isinstance(section.topic, list) else [section.topic]
        candidates = self._group_repo.find_by_metadata(
            section.subject, section.topic, section.difficulty
        )
        logger.info(
            "Retrieved %d candidate groups for section '%s' (subject=%s, topics=%s, difficulty=%s)",
            len(candidates),
            section.name,
            section.subject,
            topics,
            section.difficulty,
        )

        if not candidates:
            for fallback_diff in _DIFFICULTY_FALLBACKS.get(section.difficulty, []):
                candidates = self._group_repo.find_by_metadata(
                    section.subject, section.topic, fallback_diff
                )
                if candidates:
                    logger.info(
                        "Fell back to difficulty '%s' for section '%s' (found %d groups)",
                        fallback_diff,
                        section.name,
                        len(candidates),
                    )
                    break

        if not candidates:
            logger.warning(
                "No candidate groups found for section '%s' (subject=%s, topics=%s, difficulty=%s)",
                section.name,
                section.subject,
                topics,
                section.difficulty,
            )
            return []

        # Filter by question_type if specified
        if section.question_type:
            types_to_match = (
                section.question_type
                if isinstance(section.question_type, list)
                else [section.question_type]
            )
            filtered = []
            for group in candidates:
                # Get any question from this group to check its type
                questions = self._question_repo.get_by_group(group.id)
                if questions and any(
                    q.question_type in types_to_match for q in questions
                ):
                    filtered.append(group)

            logger.info(
                "Filtered %d → %d groups by question_type %s for section '%s'",
                len(candidates),
                len(filtered),
                types_to_match,
                section.name,
            )
            candidates = filtered

        if not candidates:
            logger.warning(
                "No candidates remaining after question_type filtering for section '%s'",
                section.name,
            )
            return []

        # If custom_text: vector-rank via cosine (no threshold — just sort)
        if section.custom_text and self._llm_client:
            query_vec = self._embed_custom_text(section.custom_text)
            if query_vec is not None:
                candidates = self._group_repo.cosine_search(
                    candidates, query_vec, threshold=0.0
                )
                return candidates[: 5 * section.top_k]

        # No custom_text: random sample pool of 5*top_k to avoid full-scan scoring
        k = min(len(candidates), 5 * section.top_k)
        return random.sample(candidates, k)

    def _embed_custom_text(self, text: Optional[str]) -> Optional[List]:
        if not text or not self._llm_client:
            return None
        try:
            embeddings = self._llm_client.embed(text)
            if embeddings and len(embeddings) > 0:
                return embeddings[0]
            return None
        except Exception as exc:
            logger.warning("Failed to embed custom_text: %s", exc)
            return None

    def _rank_questions_by_similarity(
        self, questions: List[Question], query_vec: List[float]
    ) -> List[Question]:
        """Rank questions by cosine similarity to query vector.

        Returns questions sorted by similarity (highest first), filtering out
        questions without embeddings.
        """
        import numpy as np

        scored = []
        q_vec = np.array(query_vec, dtype=float)

        for q in questions:
            if q.vector_embedding is None:
                continue
            try:
                g_vec = np.array(q.vector_embedding, dtype=float)
                cosine_sim = float(
                    np.dot(g_vec, q_vec) / (np.linalg.norm(g_vec) * np.linalg.norm(q_vec))
                )
                scored.append((q, cosine_sim))
            except Exception:
                continue

        # Sort by similarity descending
        scored.sort(key=lambda x: x[1], reverse=True)
        return [q for q, _ in scored]

    def _pick_variant(
        self,
        group: QuestionGroup,
        question_type: Optional[str | list[str]] = None,
        rng: random.Random = None,
    ) -> Optional[Question]:
        types_to_match = (
            question_type if isinstance(question_type, list) else [question_type]
        ) if question_type else None

        variants = self._question_repo.get_variants_by_group(group.id, types_to_match)
        if not variants:
            return None

        weights = [1.0 / (v.variant_existence_count + 1) for v in variants]
        total = sum(weights)
        probs = [w / total for w in weights]
        _rng = rng or random
        return _rng.choices(variants, weights=probs, k=1)[0]

    def _pick_variants(
        self,
        group: QuestionGroup,
        count: int,
        question_type: Optional[str | list[str]] = None,
    ) -> List[Question]:
        """Pick multiple distinct questions from a group with weighted sampling.

        Weight is inversely proportional to variant_existence_count.
        Returns up to 'count' questions; fewer if group has fewer eligible questions.
        """
        if count <= 0:
            return []

        types_to_match = (
            question_type if isinstance(question_type, list) else [question_type]
        ) if question_type else None

        variants = self._question_repo.get_variants_by_group(group.id, types_to_match)
        if not variants:
            return []

        selected = []
        pool = list(variants)
        k = min(count, len(pool))

        for _ in range(k):
            weights = [1.0 / (v.variant_existence_count + 1) for v in pool]
            total = sum(weights)
            probs = [w / total for w in weights]
            idx = random.choices(range(len(pool)), weights=probs, k=1)[0]
            selected.append(pool[idx])
            pool.pop(idx)

        return selected

    def _distribute_slots(self, ranked_groups: List[QuestionGroup], top_k: int) -> dict:
        """Distribute top_k slots across ranked groups proportionally.

        Pseudo Code:
            n ← len(ranked_groups)
            base_slots ← top_k / n (integer division)
            remainder ← top_k % n

            slot_map ← {}
            FOR i FROM 0 TO n-1:
                group ← ranked_groups[i]
                slots ← base_slots + (1 IF i < remainder ELSE 0)
                slot_map[group] ← slots

            RETURN slot_map

        Example: 4 groups, top_k=15 → {g0: 4, g1: 4, g2: 4, g3: 3}
        """
        if not ranked_groups:
            return {}

        n = len(ranked_groups)
        base_slots = top_k // n
        remainder = top_k % n

        return {
            group: base_slots + (1 if i < remainder else 0)
            for i, group in enumerate(ranked_groups)
        }

    def _shuffle_answers(
        self, question: Question, rng: random.Random = None
    ) -> List[int]:
        """Shuffle answer indices using timestamp-based seeding for true randomness.

        Pseudo Code:
            answers ← DB.get_by_question(question.id)
            indices ← [0, 1, 2, ..., len(answers)-1]

            IF rng IS NULL:
                seed ← current_timestamp_nanoseconds
                rng ← new Random(seed)

            rng.shuffle(indices)
            RETURN indices
        """
        answers = self._answer_repo.get_by_question(question.id)
        indices = list(range(len(answers)))

        if rng is None:
            # Use high-precision timestamp as seed for better randomness
            seed = int(time.time_ns())
            _rng = random.Random(seed)
        else:
            _rng = rng

        _rng.shuffle(indices)
        return indices
