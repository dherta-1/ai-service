from typing import Optional
from src.entities.topic import Topic
from src.shared.base.base_repo import BaseRepo


class TopicRepository(BaseRepo[Topic]):

    def __init__(self):
        super().__init__(Topic)

    def get_by_code(self, code: str) -> Optional[Topic]:
        return self.filter_one(code=code)

    def get_or_create(self, code: str, name: str) -> Topic:
        existing = self.get_by_code(code)
        if existing:
            return existing
        return self.create(code=code, name=name)
