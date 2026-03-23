from src.shared.base.base_service import BaseService
from src.repos.project_metadata_repo import ProjectMetadataRepo
from src.entities.project_metadata import ProjectMetadata


class ProjectMetadataService(BaseService):
    """Service for ProjectMetadata business logic"""

    def __init__(self, repo: ProjectMetadataRepo = None):
        if repo is None:
            repo = ProjectMetadataRepo()
        super().__init__(repo)

    def get_by_name(self, name: str) -> ProjectMetadata | None:
        """Get project metadata by name"""
        return self.repo.get_by_name(name)

    def get_by_version(self, version: str):
        """Get project metadata by version"""
        return self.repo.get_by_version(version)
