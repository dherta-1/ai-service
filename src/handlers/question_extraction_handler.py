"""question_extraction_handler – extract+embed+group+persist questions for one page."""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict
from uuid import UUID

from src.shared.base.base_handler import BaseEventHandler
from src.shared.constants.general import Status

logger = logging.getLogger(__name__)


class QuestionExtractionHandler(BaseEventHandler):
    """Handles question_extraction_requested events.

    Event payload:
    {
        "event_type": "question_extraction_requested",
        "page_id": str(UUID),
        "task_id": str(UUID),
        "is_final_page": bool
    }
    """

    @property
    def event_type(self) -> str:
        return "question_extraction_requested"

    @property
    def topic(self) -> str:
        return "question_extraction_requested"

    def __init__(self):
        from src.services.core.question_extraction_service import (
            QuestionExtractionService,
        )
        from src.container import get_di_container

        container = get_di_container()
        self._service = QuestionExtractionService(
            llm_client=container.get("llm_client")
        )

    def handle(self, key: str, value: Dict[str, Any]) -> None:
        asyncio.run(self._handle_async(value))

    async def _handle_async(self, value: Dict[str, Any]) -> None:
        from src.repos.task_repo import TaskRepository
        from src.repos.document_repo import DocumentRepository

        page_id = UUID(value["page_id"])
        task_id = UUID(value["task_id"])
        is_final_page = bool(value.get("is_final_page", False))
        uploaded_by_id_str = value.get("uploaded_by_id")
        uploaded_by_id = UUID(uploaded_by_id_str) if uploaded_by_id_str else None

        task_repo = TaskRepository()

        try:
            result = await self._service.process_page(
                page_id=page_id,
                task_id=task_id,
                is_final_page=is_final_page,
                uploaded_by_id=uploaded_by_id,
            )

            logger.info(
                "Question extraction complete for page %s (final=%s, persisted=%d)",
                page_id,
                is_final_page,
                result.get("persisted_count", 0),
            )

            if is_final_page:
                task = task_repo.get_by_id(task_id)
                if task and task.entity_id:
                    doc_repo = DocumentRepository()
                    doc_repo.update(
                        task.entity_id, status=Status.COMPLETED.value, progress=1.0
                    )
                    task_repo.update_status(task_id, Status.COMPLETED.value)
                    logger.info(
                        "Document %s marked as COMPLETED (%d questions extracted)",
                        task.entity_id,
                        result.get("persisted_count", 0),
                    )

        except Exception as exc:
            logger.error(
                "Question extraction failed for page %s: %s",
                page_id,
                exc,
                exc_info=True,
            )
            task_repo.update_status(task_id, Status.FAILED.value)
