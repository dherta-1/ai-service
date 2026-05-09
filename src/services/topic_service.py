from typing import Optional
from src.repos.topic_repo import TopicRepository
from src.dtos.topic.res import TopicResponse
from src.shared.helpers.dto_utils import to_dict


class TopicService:
    """Service for topic-related operations"""

    def __init__(self, topic_repo: TopicRepository):
        self._repo = topic_repo

    def search(
        self,
        query: Optional[str] = None,
        subject_code: Optional[str] = None,
        page: int = 1,
        page_size: int = 10
    ) -> tuple[list[TopicResponse], int]:
        """Search topics with optional subject filter and pagination"""
        topics, total_count = self._repo.search(
            query=query,
            subject_code=subject_code,
            page=page,
            page_size=page_size
        )
        return [TopicResponse(**to_dict(t)) for t in topics], total_count

    def get_by_subject(self, subject_code: str) -> list[TopicResponse]:
        """Get all topics for a subject"""
        topics = self._repo.get_by_subject(subject_code)
        return [TopicResponse(**to_dict(t)) for t in topics]

    def get_all(self) -> list[TopicResponse]:
        """Get all topics without pagination"""
        topics = self._repo.get_all()
        return [TopicResponse(**to_dict(t)) for t in topics]

    def get_by_code(self, code: str) -> Optional[TopicResponse]:
        """Get topic by code"""
        topic = self._repo.get_by_code(code)
        if topic:
            return TopicResponse(**to_dict(topic))
        return None
