from typing import Optional
from src.entities.topic import Topic
from src.shared.base.base_repo import BaseRepo


class TopicRepository(BaseRepo[Topic]):

    def __init__(self):
        super().__init__(Topic)

    def get_by_code(self, code: str) -> Optional[Topic]:
        return self.filter_one(code=code)

    def get_or_create(
        self,
        code: str,
        name: str,
        name_vi: Optional[str] = None,
        subject_code: Optional[str] = None,
    ) -> Topic:
        existing = self.get_by_code(code)
        if existing:
            return existing
        return self.create(
            code=code, name=name, name_vi=name_vi, subject_code=subject_code
        )

    def search(
        self,
        query: Optional[str] = None,
        subject_code: Optional[str] = None,
        page: int = 1,
        page_size: int = 10
    ) -> tuple[list[Topic], int]:
        """Search topics with optional filters by name/code and subject"""
        q = self.model.select()

        if query:
            q = q.where(
                (self.model.name.contains(query)) |
                (self.model.code.contains(query)) |
                (self.model.name_vi.contains(query))
            )

        if subject_code:
            q = q.where(self.model.subject_code == subject_code)

        total_count = q.count()
        offset = (page - 1) * page_size
        results = list(q.offset(offset).limit(page_size))

        return results, total_count

    def get_by_subject(self, subject_code: str) -> list[Topic]:
        """Get all topics for a subject"""
        return self.filter(subject_code=subject_code)
