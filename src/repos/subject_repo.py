from typing import Optional
from src.entities.subject import Subject
from src.shared.base.base_repo import BaseRepo


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
