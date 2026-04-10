from typing import List, Optional
from uuid import UUID
from src.entities.page import Page
from src.shared.base.base_repo import BaseRepo


class PageRepository(BaseRepo[Page]):

    def __init__(self):
        super().__init__(Page)

    def get_by_document(self, document_id: UUID) -> List[Page]:
        return self.filter(document=document_id)

    def get_by_document_and_page_number(
        self, document_id: UUID, page_number: int
    ) -> Optional[Page]:
        return self.filter_one(document=document_id, page_number=page_number)

    def get_by_page_number(self, page_number: int) -> List[Page]:
        return self.filter(page_number=page_number)
