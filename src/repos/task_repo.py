from typing import List
from uuid import UUID
from src.entities.task import Task
from src.shared.base.base_repo import BaseRepo
from src.shared.constants.general import Status


class TaskRepository(BaseRepo[Task]):

    def __init__(self):
        super().__init__(Task)

    def get_by_document(self, document_id: UUID) -> List[Task]:
        return self.filter(document=document_id)

    def get_pending(self) -> List[Task]:
        return self.filter(status=Status.PENDING.value)

    def update_status(self, task_id: UUID, status: str) -> Task | None:
        return self.update(task_id, status=status)

    def update_progress(self, task_id: UUID, progress: float) -> Task | None:
        return self.update(task_id, progress=progress)
