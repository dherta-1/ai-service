from __future__ import annotations

import base64
import hmac
import json
from datetime import datetime
from hashlib import sha256
from typing import List, Optional
from uuid import UUID

from src.dtos.exam.req import SectionConfig
from src.entities.exam_instance import ExamInstance
from src.entities.user import User
from src.repos.answer_repo import AnswerRepository
from src.repos.exam_instance_repo import ExamInstanceRepository
from src.repos.exam_template_repo import ExamTemplateRepository
from src.repos.exam_test_section_repo import ExamTestSectionRepository
from src.repos.question_exam_test_repo import QuestionExamTestRepository
from src.repos.question_repo import QuestionRepository
from src.repos.user_test_attempt_answer_repo import UserTestAttemptAnswerRepository
from src.repos.user_test_attempt_repo import UserTestAttemptRepository
from src.services.answer_scoring_service import AnswerScoringService
from src.services.core.base_exam_generation_service import BaseExamGenerationService
from src.services.token_service import ExamTokenService
from src.settings import get_settings
from src.shared.constants.exam import ExamInstanceStatus, UserTestAttemptStatus

ELIGIBLE_QUESTION_TYPES = {"multiple_choice", "true_false", "selection"}


class ExamAttemptService:
    def __init__(self):
        self._template_repo = ExamTemplateRepository()
        self._instance_repo = ExamInstanceRepository()
        self._section_repo = ExamTestSectionRepository()
        self._qet_repo = QuestionExamTestRepository()
        self._question_repo = QuestionRepository()
        self._answer_repo = AnswerRepository()
        self._attempt_repo = UserTestAttemptRepository()
        self._attempt_answer_repo = UserTestAttemptAnswerRepository()
        self._token_service = ExamTokenService()
        self._scoring_service = AnswerScoringService()
        self._base_exam_service = BaseExamGenerationService(llm_client=None)
        self._settings = get_settings()

    def start_attempt(
        self,
        template_id: UUID,
        user: User,
        use_existing_instance: bool = False,
    ) -> dict:
        template = self._template_repo.get_by_id(template_id)
        if not template:
            raise ValueError("Template not found")

        if use_existing_instance:
            # Try to randomly select an existing instance from the template
            instance = self._instance_repo.get_random_instance(template_id)
            if not instance:
                raise ValueError(
                    "No eligible exam instances available for this template"
                )
            if instance.status == ExamInstanceStatus.REJECTED:
                raise ValueError("Selected exam instance is not eligible")
            self._ensure_instance_eligible(instance)
        else:
            if not template.generation_config:
                raise ValueError("Template has no generation config")
            sections = self._load_sections(template.generation_config)
            instance = self._base_exam_service.generate_base_exam(
                sections=sections,
                template_id=template_id,
                created_by_id=user.id,
            )
            self._ensure_instance_eligible(instance)

        attempt = self._attempt_repo.create_attempt(
            user_id=user.id,
            exam_template_id=template_id,
            exam_instance_id=instance.id,
        )

        attempt_token = self._token_service.generate_attempt_token(str(attempt.id))
        questions, _ = self._build_questions_payload(attempt.id, instance)

        return {
            "attempt_token": attempt_token,
            "expires_at": self._resolve_expires_at(attempt_token).isoformat(),
            "started_at": attempt.started_at.isoformat(),
            "total_questions": len(questions),
            "questions": questions,
        }

    def start_attempt_from_instance(self, instance_id: UUID, user: User) -> dict:
        instance = self._instance_repo.get_by_id(instance_id)
        if not instance:
            raise ValueError("Exam instance not found")
        if instance.status == ExamInstanceStatus.REJECTED:
            raise ValueError("Exam instance is not eligible")
        self._ensure_instance_eligible(instance)

        attempt = self._attempt_repo.create_attempt(
            user_id=user.id,
            exam_template_id=UUID(str(instance.exam_template_id)),
            exam_instance_id=instance.id,
        )

        attempt_token = self._token_service.generate_attempt_token(str(attempt.id))
        questions, _ = self._build_questions_payload(attempt.id, instance)

        return {
            "attempt_token": attempt_token,
            "expires_at": self._resolve_expires_at(attempt_token).isoformat(),
            "started_at": attempt.started_at.isoformat(),
            "total_questions": len(questions),
            "questions": questions,
        }

    def get_current_attempt(self, token: str, user: User) -> dict:
        mapping = self._token_service.validate_attempt_token(token)
        if not mapping:
            raise ValueError("Invalid or expired token")

        attempt = self._attempt_repo.get_by_user(UUID(mapping.attempt_id), user.id)
        if not attempt:
            raise ValueError("Attempt not found")

        if attempt.status == UserTestAttemptStatus.SUBMITTED:
            raise ValueError("Exam already submitted")

        if attempt.status == UserTestAttemptStatus.EXPIRED:
            raise ValueError("Exam attempt expired")

        instance = self._instance_repo.get_by_id(attempt.exam_instance_id)
        if not instance:
            raise ValueError("Exam instance not found")

        questions, _ = self._build_questions_payload(attempt.id, instance)
        answered_count = len(
            [
                a
                for a in self._attempt_answer_repo.get_by_attempt(attempt.id)
                if a.selected_answer_id
            ]
        )
        time_elapsed_ms = int(
            (datetime.utcnow() - attempt.started_at).total_seconds() * 1000
        )

        return {
            "attempt_token": token,
            "status": "in_progress",
            "started_at": attempt.started_at.isoformat(),
            "expires_at": self._resolve_expires_at(token).isoformat(),
            "time_elapsed_ms": time_elapsed_ms,
            "total_questions": len(questions),
            "answered_count": answered_count,
            "questions": questions,
        }

    def save_answer(
        self,
        token: str,
        user: User,
        question_token: str,
        selected_option_token: Optional[str],
    ) -> None:
        mapping = self._token_service.validate_attempt_token(token)
        if not mapping:
            raise ValueError("Invalid or expired token")

        attempt = self._attempt_repo.get_by_user(UUID(mapping.attempt_id), user.id)
        if not attempt:
            raise ValueError("Attempt not found")

        if attempt.status != UserTestAttemptStatus.SUBMITTED:
            raise ValueError("Exam not submitted")
        if attempt.status != UserTestAttemptStatus.IN_PROGRESS:
            raise ValueError("Attempt is not active")

        instance = self._instance_repo.get_by_id(attempt.exam_instance_id)
        if not instance:
            raise ValueError("Exam instance not found")

        question_id = self._resolve_question_id(attempt.id, instance, question_token)
        if not question_id:
            raise ValueError("Question token invalid")

        selected_answer_id = None
        if selected_option_token:
            selected_answer_id = self._resolve_answer_id(
                attempt.id, question_id, selected_option_token
            )
            if not selected_answer_id:
                raise ValueError("Option token invalid")

        self._attempt_answer_repo.upsert_answer(
            attempt_id=attempt.id,
            question_id=question_id,
            selected_answer_id=selected_answer_id,
            is_correct=False,
        )

    def submit_attempt(self, token: str, user: User, answers: List[dict]) -> dict:
        mapping = self._token_service.validate_attempt_token(token)
        if not mapping:
            raise ValueError("Invalid or expired token")

        attempt = self._attempt_repo.get_by_user(UUID(mapping.attempt_id), user.id)
        if not attempt:
            raise ValueError("Attempt not found")

        if attempt.status == UserTestAttemptStatus.SUBMITTED:
            raise ValueError("Exam already submitted")

        instance = self._instance_repo.get_by_id(attempt.exam_instance_id)
        if not instance:
            raise ValueError("Exam instance not found")

        normalized_answers = self._normalize_submitted_answers(
            attempt.id, instance, answers
        )
        if not normalized_answers:
            raise ValueError("No answers provided")

        correct_count, scored = self._scoring_service.score_answers(normalized_answers)
        total_questions = len(self._collect_question_ids(instance))
        score = (
            round((correct_count / total_questions) * 100, 2) if total_questions else 0
        )

        for scored_answer in scored:
            self._attempt_answer_repo.upsert_answer(
                attempt_id=attempt.id,
                question_id=scored_answer["question_id"],
                selected_answer_id=scored_answer.get("selected_answer_id"),
                is_correct=scored_answer["is_correct"],
            )

        submitted_at = datetime.utcnow()
        self._attempt_repo.update_status(
            attempt_id=attempt.id,
            status=UserTestAttemptStatus.SUBMITTED,
            score=score,
            submitted_at=submitted_at,
        )

        self._token_service.invalidate_token(token)

        return {
            "status": "submitted",
            "submitted_at": submitted_at.isoformat(),
            "score": score,
            "total_questions": total_questions,
            "correct_count": correct_count,
            "result_available": True,
        }

    def list_user_attempts(
        self, user: User, page: int = 1, per_page: int = 10
    ) -> tuple[list[dict], int]:
        attempts, total = self._attempt_repo.list_by_user(user.id, page, per_page)
        template_ids = list(
            {a.exam_template_id for a in attempts if a.exam_template_id}
        )
        templates = {str(t.id): t for t in self._template_repo.get_by_ids(template_ids)}
        data = []
        for attempt in attempts:
            tmpl = templates.get(str(attempt.exam_template_id))
            data.append(
                {
                    "id": str(attempt.id),
                    "exam_template_id": attempt.exam_template_id,
                    "template_name": tmpl.name if tmpl else None,
                    "template_subject": tmpl.subject if tmpl else None,
                    "status": attempt.status,
                    "score": (
                        float(attempt.score) if attempt.score is not None else None
                    ),
                    "started_at": attempt.started_at.isoformat(),
                    "submitted_at": (
                        attempt.submitted_at.isoformat()
                        if attempt.submitted_at
                        else None
                    ),
                }
            )
        return data, total

    def get_attempt_detail(self, attempt_id: UUID, user: User) -> dict:
        attempt = self._attempt_repo.get_by_user(attempt_id, user.id)
        if not attempt:
            raise ValueError("Attempt not found")

        answers = self._attempt_answer_repo.get_by_attempt(attempt.id)
        instance = self._instance_repo.get_by_id(attempt.exam_instance_id)
        if not instance:
            raise ValueError("Exam instance not found")

        question_no_map = {}
        question_text_map = {}
        correct_answer_map = {}
        answer_text_map = {}

        question_no = 1
        sections = self._section_repo.get_by_exam_instance(instance.id)
        for sec in sections:
            qets = self._qet_repo.get_by_section(sec.id)
            for qet in qets:
                question = self._question_repo.get_by_id(UUID(qet.question_id))
                if not question or question.parent_question_id:
                    continue
                if question.question_type not in ELIGIBLE_QUESTION_TYPES:
                    continue
                question_no_map[str(question.id)] = question_no
                question_text_map[str(question.id)] = question.question_text
                for ans in self._answer_repo.get_by_question(question.id):
                    answer_text_map[str(ans.id)] = ans.value
                    if ans.is_correct:
                        correct_answer_map[str(question.id)] = ans.value
                question_no += 1

        details = []
        for answer in answers:
            qid = answer.question_id
            if qid not in question_no_map:
                continue
            details.append(
                {
                    "question_no": question_no_map[qid],
                    "question_text": question_text_map.get(qid),
                    "selected_answer": (
                        answer_text_map.get(answer.selected_answer_id)
                        if answer.selected_answer_id
                        else None
                    ),
                    "correct_answer": correct_answer_map.get(qid),
                    "is_correct": answer.is_correct,
                }
            )
        details.sort(key=lambda d: d["question_no"])

        tmpl = (
            self._template_repo.get_by_id(UUID(attempt.exam_template_id))
            if attempt.exam_template_id
            else None
        )
        return {
            "id": str(attempt.id),
            "template_name": tmpl.name if tmpl else None,
            "template_subject": tmpl.subject if tmpl else None,
            "status": attempt.status,
            "score": float(attempt.score) if attempt.score is not None else None,
            "started_at": attempt.started_at.isoformat(),
            "submitted_at": (
                attempt.submitted_at.isoformat() if attempt.submitted_at else None
            ),
            "total_questions": len(question_no_map),
            "correct_count": len([d for d in details if d["is_correct"]]),
            "details": details,
        }

    def get_result(self, token: str, user: User) -> dict:
        mapping = self._token_service.validate_attempt_token(
            token, allow_invalidated=True
        )
        if not mapping:
            raise ValueError("Invalid or expired token")

        attempt = self._attempt_repo.get_by_user(UUID(mapping.attempt_id), user.id)
        if not attempt:
            raise ValueError("Attempt not found")

        answers = self._attempt_answer_repo.get_by_attempt(attempt.id)
        instance = self._instance_repo.get_by_id(attempt.exam_instance_id)
        if not instance:
            raise ValueError("Exam instance not found")

        question_no_map = self._build_question_no_map(instance)
        details = []
        for answer in answers:
            details.append(
                {
                    "question_id": answer.question_id,
                    "question_no": question_no_map.get(answer.question_id, 0),
                    "selected_answer_id": answer.selected_answer_id,
                    "is_correct": answer.is_correct,
                }
            )

        return {
            "score": float(attempt.score) if attempt.score is not None else None,
            "total_questions": len(question_no_map),
            "correct_count": len([d for d in details if d["is_correct"]]),
            "submitted_at": (
                attempt.submitted_at.isoformat() if attempt.submitted_at else None
            ),
            "review_available": True,
            "details": details,
        }

    def _load_sections(self, config_json: str) -> List[SectionConfig]:
        raw = json.loads(config_json)
        sections = [SectionConfig(**item) for item in raw]
        normalized: List[SectionConfig] = []
        for section in sections:
            normalized.append(self._normalize_section(section))
        return normalized

    def _normalize_section(self, section: SectionConfig) -> SectionConfig:
        if section.question_type is None:
            section.question_type = list(ELIGIBLE_QUESTION_TYPES)
            return section

        types = (
            section.question_type
            if isinstance(section.question_type, list)
            else [section.question_type]
        )
        # Filter to only eligible types instead of rejecting
        eligible_types = [t for t in types if t in ELIGIBLE_QUESTION_TYPES]
        section.question_type = (
            eligible_types if eligible_types else list(ELIGIBLE_QUESTION_TYPES)
        )
        return section

    def _ensure_instance_eligible(self, instance: ExamInstance) -> None:
        """Validate instance has at least some eligible questions"""
        question_ids = self._collect_question_ids(instance)
        if not question_ids:
            raise ValueError("Instance has no questions")

        eligible_count = 0
        for qid in question_ids:
            question = self._question_repo.get_by_id(UUID(qid))
            if question and question.question_type in ELIGIBLE_QUESTION_TYPES:
                eligible_count += 1

        if eligible_count == 0:
            raise ValueError("Instance contains no eligible question types")

    def _collect_question_ids(self, instance: ExamInstance) -> List[str]:
        qets = self._qet_repo.get_by_exam_instance(instance.id)
        return [qet.question_id for qet in qets]

    def _build_questions_payload(
        self, attempt_id: UUID, instance: ExamInstance
    ) -> tuple[List[dict], dict[str, int]]:
        questions: List[dict] = []
        question_no_map: dict[str, int] = {}
        question_no = 1

        sections = self._section_repo.get_by_exam_instance(instance.id)
        for sec in sections:
            qets = self._qet_repo.get_by_section(sec.id)
            for qet in qets:
                question = self._question_repo.get_by_id(UUID(qet.question_id))
                if not question or question.parent_question_id:
                    continue

                # Skip ineligible question types instead of rejecting
                if question.question_type not in ELIGIBLE_QUESTION_TYPES:
                    continue

                answers = self._answer_repo.get_by_question(question.id)
                ordered_answers = self._apply_answer_order(answers, qet.answer_order)

                question_token = self._make_question_token(attempt_id, str(question.id))
                options = []
                for ans in ordered_answers:
                    option_token = self._make_option_token(
                        attempt_id, str(question.id), str(ans.id)
                    )
                    options.append(
                        {
                            "option_token": option_token,
                            "content": ans.value,
                        }
                    )

                questions.append(
                    {
                        "question_no": question_no,
                        "question_token": question_token,
                        "question_text": question.question_text,
                        "question_type": question.question_type,
                        "image_list": question.image_list,
                        "options": options,
                    }
                )
                question_no_map[str(question.id)] = question_no
                question_no += 1

        return questions, question_no_map

    def _build_question_no_map(self, instance: ExamInstance) -> dict[str, int]:
        qets = self._qet_repo.get_by_exam_instance(instance.id)
        question_no_map: dict[str, int] = {}
        question_no = 1
        for qet in qets:
            question_no_map[qet.question_id] = question_no
            question_no += 1
        return question_no_map

    def _apply_answer_order(self, answers, answer_order_raw: Optional[str]) -> List:
        if not answer_order_raw:
            return list(answers)
        try:
            order = json.loads(answer_order_raw)
        except (ValueError, TypeError):
            return list(answers)

        ordered: List = []
        answer_list = list(answers)
        for idx in order:
            if 0 <= idx < len(answer_list):
                ordered.append(answer_list[idx])
        if len(ordered) != len(answer_list):
            return answer_list
        return ordered

    def _resolve_question_id(
        self, attempt_id: UUID, instance: ExamInstance, question_token: str
    ) -> Optional[str]:
        qets = self._qet_repo.get_by_exam_instance(instance.id)
        for qet in qets:
            token = self._make_question_token(attempt_id, qet.question_id)
            if hmac.compare_digest(token, question_token):
                return qet.question_id
        return None

    def _resolve_answer_id(
        self, attempt_id: UUID, question_id: str, option_token: str
    ) -> Optional[str]:
        answers = self._answer_repo.get_by_question(UUID(question_id))
        for ans in answers:
            token = self._make_option_token(attempt_id, question_id, str(ans.id))
            if hmac.compare_digest(token, option_token):
                return str(ans.id)
        return None

    def _normalize_submitted_answers(
        self, attempt_id: UUID, instance: ExamInstance, answers: List
    ) -> List[dict]:
        normalized = []
        for answer in answers:
            # Handle both dict and Pydantic model objects
            question_token = (
                answer.question_token
                if hasattr(answer, "question_token")
                else answer.get("question_token")
            )
            option_token = (
                answer.selected_option_token
                if hasattr(answer, "selected_option_token")
                else answer.get("selected_option_token")
            )
            if not question_token:
                continue

            question_id = self._resolve_question_id(
                attempt_id, instance, question_token
            )
            if not question_id:
                continue

            selected_answer_id = None
            if option_token:
                selected_answer_id = self._resolve_answer_id(
                    attempt_id, question_id, option_token
                )

            normalized.append(
                {
                    "question_id": question_id,
                    "selected_answer_id": selected_answer_id,
                }
            )

        return normalized

    def _make_question_token(self, attempt_id: UUID, question_id: str) -> str:
        raw = f"{attempt_id}:{question_id}:question"
        return self._sign_token(raw)

    def _make_option_token(
        self, attempt_id: UUID, question_id: str, answer_id: str
    ) -> str:
        raw = f"{attempt_id}:{question_id}:{answer_id}:option"
        return self._sign_token(raw)

    def _sign_token(self, raw: str) -> str:
        digest = hmac.new(
            self._settings.jwt_secret_key.encode(),
            raw.encode(),
            sha256,
        ).digest()
        return base64.urlsafe_b64encode(digest).decode().rstrip("=")

    def _resolve_expires_at(self, token: str) -> datetime:
        mapping = self._token_service.validate_attempt_token(
            token, allow_invalidated=True
        )
        if not mapping:
            return datetime.utcnow()
        return mapping.expires_at
