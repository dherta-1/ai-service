from typing import List, Optional
from uuid import UUID
from src.shared.base.base_service import BaseService
from src.repos.document_repo import DocumentRepository


class DocumentService(BaseService):
    """Service for document operations"""

    def __init__(self):
        super().__init__(DocumentRepository())

    def get_by_id(self, document_id: UUID) -> Optional:
        """Get document by ID"""
        return self.repo.get_by_id(document_id)

    def get_all(self) -> List:
        """Get all documents"""
        return self.repo.get_all()

    def get_all_paginated(self, page: int = 1, page_size: int = 10):
        """Get documents with pagination"""
        return self.repo.get_all_paginated(page, page_size)

    def get_by_file_id(self, file_id: str) -> Optional:
        """Get document by file ID"""
        return self.repo.get_by_file_id(file_id)

    def get_by_name(self, name: str) -> Optional:
        """Get document by name"""
        return self.repo.get_by_name(name)

    def get_by_status(self, status: str) -> List:
        """Get documents by status"""
        return self.repo.get_by_status(status)

    def get_pending(self) -> List:
        """Get pending documents"""
        return self.repo.get_pending()
