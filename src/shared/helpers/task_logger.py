from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

logger = logging.getLogger(__name__)


class TaskLogger:
    """Append-only structured logger that writes to task.logs (JSONB)."""

    def __init__(self, task_repo):
        self._task_repo = task_repo

    def append(self, task_id: UUID, event: dict) -> None:
        try:
            self._task_repo.append_log(task_id, event)
        except Exception as exc:
            logger.warning("Failed to write task log for %s: %s", task_id, exc)

    def log_page_processed(
        self,
        task_id: UUID,
        page_number: int,
        questions_count: int,
        duration_ms: int,
    ) -> None:
        self.append(
            task_id,
            {
                "event": "page_processed",
                "page_number": page_number,
                "questions_count": questions_count,
                "duration_ms": duration_ms,
                "status": "success",
            },
        )

    def log_page_failed(
        self,
        task_id: UUID,
        page_number: int,
        error: str,
    ) -> None:
        self.append(
            task_id,
            {
                "event": "page_failed",
                "page_number": page_number,
                "error": error,
                "status": "error",
            },
        )

    def log_error(
        self,
        task_id: UUID,
        error_msg: str,
        page_number: Optional[int] = None,
    ) -> None:
        entry: dict = {"event": "error", "message": error_msg}
        if page_number is not None:
            entry["page_number"] = page_number
        self.append(task_id, entry)

    def log_started(self, task_id: UUID, total_pages: int) -> None:
        self.append(
            task_id,
            {"event": "extraction_started", "total_pages": total_pages},
        )

    def log_completed(self, task_id: UUID, total_questions: int) -> None:
        self.append(
            task_id,
            {"event": "extraction_completed", "total_questions": total_questions},
        )
