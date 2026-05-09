from typing import Optional
from src.repos.subject_repo import SubjectRepository
from src.dtos.subject.res import SubjectResponse
from src.shared.helpers.dto_utils import to_dict


class SubjectService:
    """Service for subject-related operations"""

    def __init__(self, subject_repo: SubjectRepository):
        self._repo = subject_repo

    def search(
        self,
        query: Optional[str] = None,
        page: int = 1,
        page_size: int = 10
    ) -> tuple[list[SubjectResponse], int]:
        """Search subjects with pagination"""
        subjects, total_count = self._repo.search(
            query=query,
            page=page,
            page_size=page_size
        )
        return [SubjectResponse(**to_dict(s)) for s in subjects], total_count

    def get_all(self) -> list[SubjectResponse]:
        """Get all subjects without pagination"""
        subjects = self._repo.get_all()
        return [SubjectResponse(**to_dict(s)) for s in subjects]

    def get_by_code(self, code: str) -> Optional[SubjectResponse]:
        """Get subject by code"""
        subject = self._repo.get_by_code(code)
        if subject:
            return SubjectResponse(**to_dict(subject))
        return None
