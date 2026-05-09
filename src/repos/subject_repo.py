from typing import Optional
from src.entities.subject import Subject
from src.shared.base.base_repo import BaseRepo
from peewee import fn


class SubjectRepository(BaseRepo[Subject]):

    def __init__(self):
        super().__init__(Subject)

    def get_by_code(self, code: str) -> Optional[Subject]:
        return self.filter_one(code=code)

    def get_or_create(self, code: str, name: str, name_vi: Optional[str] = None) -> Subject:
        existing = self.get_by_code(code)
        if existing:
            return existing
        return self.create(code=code, name=name, name_vi=name_vi)

    def search(
        self,
        query: Optional[str] = None,
        page: int = 1,
        page_size: int = 10
    ) -> tuple[list[Subject], int]:
        """Search subjects by name/code with pagination"""
        q = self.model.select()

        if query:
            search_term = f"%{query}%"
            q = q.where(
                (self.model.name.contains(query)) |
                (self.model.code.contains(query)) |
                (self.model.name_vi.contains(query))
            )

        total_count = q.count()
        offset = (page - 1) * page_size
        results = list(q.offset(offset).limit(page_size))

        return results, total_count
