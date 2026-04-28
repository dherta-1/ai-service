from __future__ import annotations

from typing import List, Optional
from uuid import UUID

from src.entities.task import Task
from src.shared.base.base_repo import BaseRepo
from src.shared.constants.general import Status


class TaskRepository(BaseRepo[Task]):

    def __init__(self):
        super().__init__(Task)

    def get_by_document(self, document_id: UUID) -> List[Task]:
        return list(Task.select().where(Task.document == document_id))

    def get_latest_by_document(self, document_id: UUID) -> Optional[Task]:
        try:
            return (
                Task.select()
                .where(Task.document == document_id)
                .order_by(Task.created_at.desc())
                .get()
            )
        except Task.DoesNotExist:
            return None

    def get_pending(self) -> List[Task]:
        return list(Task.select().where(Task.status == Status.PENDING.value))

    def update_status(self, task_id: UUID, status: str) -> Optional[Task]:
        return self.update(task_id, status=status)

    def update_progress(self, task_id: UUID, progress: float) -> Optional[Task]:
        return self.update(task_id, progress=progress)

    def increment_processed_pages(self, task_id: UUID) -> Optional[Task]:
        Task.update(
            processed_pages=Task.processed_pages + 1
        ).where(Task.id == task_id).execute()
        return self.get_by_id(task_id)

    def append_log(self, task_id: UUID, entry: dict) -> None:
        from datetime import datetime, timezone
        task = self.get_by_id(task_id)
        if task is None:
            return
        logs = task.logs or []
        logs.append({"timestamp": datetime.now(timezone.utc).isoformat(), **entry})
        task.logs = logs
        task.save()
