from typing import List, Optional
from uuid import UUID
from src.shared.base.base_service import BaseService
from src.repos.page_repo import PageRepository


class PageService(BaseService):
    """Service for page operations"""

    def __init__(self):
        super().__init__(PageRepository())

    def get_by_id(self, page_id: UUID) -> Optional:
        """Get page by ID"""
        return self.repo.get_by_id(page_id)

    def get_all(self) -> List:
        """Get all pages"""
        return self.repo.get_all()

    def get_all_paginated(self, page: int = 1, page_size: int = 10):
        """Get pages with pagination"""
        return self.repo.get_all_paginated(page, page_size)

    def get_by_document(self, document_id: UUID) -> List:
        """Get pages by document ID"""
        return self.repo.get_by_document(document_id)

    def get_by_document_and_page_number(
        self, document_id: UUID, page_number: int
    ) -> Optional:
        """Get page by document ID and page number"""
        return self.repo.get_by_document_and_page_number(document_id, page_number)

    def get_by_page_number(self, page_number: int) -> List:
        """Get pages by page number"""
        return self.repo.get_by_page_number(page_number)
