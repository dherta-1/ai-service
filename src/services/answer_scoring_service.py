from __future__ import annotations

from typing import Iterable, List, Optional

from src.repos.answer_repo import AnswerRepository


class AnswerScoringService:
    def __init__(self):
        self._answer_repo = AnswerRepository()

    def score_answers(self, answers: Iterable[dict]) -> tuple[int, List[dict]]:
        correct_count = 0
        results: List[dict] = []

        for answer in answers:
            question_id = answer["question_id"]
            selected_answer_id = answer.get("selected_answer_id")
            correct_ids = [
                str(a.id)
                for a in self._answer_repo.get_by_question(question_id)
                if a.is_correct
            ]
            is_correct = (
                selected_answer_id is not None and selected_answer_id in correct_ids
            )
            if is_correct:
                correct_count += 1

            results.append(
                {
                    "question_id": question_id,
                    "selected_answer_id": selected_answer_id,
                    "is_correct": is_correct,
                    "correct_answer_ids": correct_ids,
                }
            )

        return correct_count, results

    def build_result_details(
        self,
        answers: Iterable[dict],
        question_no_map: dict[str, int],
    ) -> List[dict]:
        details: List[dict] = []
        for answer in answers:
            question_id = answer["question_id"]
            question_no = question_no_map.get(question_id, 0)
            details.append(
                {
                    "question_id": question_id,
                    "question_no": question_no,
                    "selected_answer_id": answer.get("selected_answer_id"),
                    "is_correct": answer.get("is_correct", False),
                    "correct_answer_ids": answer.get("correct_answer_ids", []),
                }
            )
        return details
