from __future__ import annotations

from typing import Optional, Any
from uuid import UUID

from src.repos.task_repo import TaskRepository
from src.shared.base.base_service import BaseService


class TaskService(BaseService):
    """Task management service for document extraction tasks."""

    def __init__(self):
        super().__init__(TaskRepository())

    def get_by_id(self, task_id: UUID) -> Optional[Any]:
        return self.repo.get_by_id(task_id)

    def get_latest_by_document(self, document_id: UUID) -> Optional[Any]:
        """Get the latest extraction task for a document."""
        return self.repo.get_latest_by_document(document_id)

    def get_by_document(self, document_id: UUID) -> list:
        """Get all extraction tasks for a document."""
        return self.repo.get_by_document(document_id)

    def get_by_status(self, status: str) -> list:
        """Get all tasks with a specific status."""
        return self.repo.get_by_status(status)
