from typing import Optional
from src.entities.file_metadata import FileMetadata
from src.shared.base.base_repo import BaseRepo


class FileMetadataRepository(BaseRepo[FileMetadata]):

    def __init__(self):
        super().__init__(FileMetadata)

    def get_by_path(self, path: str) -> Optional[FileMetadata]:
        return self.filter_one(path=path)

    def get_by_object_key(self, object_key: str) -> Optional[FileMetadata]:
        return self.filter_one(object_key=object_key)
