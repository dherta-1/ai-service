from src.shared.base.base_repo import BaseRepo
from src.entities.project_metadata import ProjectMetadata


class ProjectMetadataRepo(BaseRepo[ProjectMetadata]):
    """Repository for ProjectMetadata entity"""

    def __init__(self):
        super().__init__(ProjectMetadata)

    def get_by_name(self, name: str) -> ProjectMetadata | None:
        """Get project by name"""
        return self.filter_one(name=name)

    def get_by_version(self, version: str):
        """Get projects by version"""
        return self.filter(version=version)
