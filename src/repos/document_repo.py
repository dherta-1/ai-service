from typing import List, Optional, Tuple
from uuid import UUID
from src.entities.document import Document
from src.shared.base.base_repo import BaseRepo
from src.shared.constants.general import Status


class DocumentRepository(BaseRepo[Document]):

    def __init__(self):
        super().__init__(Document)

    def get_by_file_id(self, file_id: str) -> Optional[Document]:
        return self.filter_one(file_id=file_id)

    def get_by_name(self, name: str) -> Optional[Document]:
        return self.filter_one(name=name)

    def get_by_status(self, status: str) -> List[Document]:
        return self.filter(status=status)

    def get_pending(self) -> List[Document]:
        return self.get_by_status(Status.PENDING.value)

    def get_all_paginated_by_user(self, uploaded_by_id: UUID, page: int = 1, page_size: int = 10) -> Tuple[List[Document], int]:
        """Get paginated documents for a specific user"""
        query = Document.select().where(Document.uploaded_by_id == uploaded_by_id)
        total = query.count()
        offset = (page - 1) * page_size
        documents = list(query.offset(offset).limit(page_size))
        return documents, total
