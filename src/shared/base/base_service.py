from src.shared.base.base_repo import BaseRepo


class BaseService:
    """Base service class for business logic operations"""

    def __init__(self, repo: BaseRepo):
        self.repo = repo

    def create(self, **kwargs):
        """Create entity via repository"""
        return self.repo.create(**kwargs)

    def get_by_id(self, entity_id):
        """Get entity by ID via repository"""
        return self.repo.get_by_id(entity_id)

    def get_all(self):
        """Get all entities via repository"""
        return self.repo.get_all()

    def update(self, entity_id, **kwargs):
        """Update entity via repository"""
        return self.repo.update(entity_id, **kwargs)

    def delete(self, entity_id):
        """Delete entity via repository"""
        return self.repo.delete(entity_id)

    def exists(self, **kwargs):
        """Check entity existence via repository"""
        return self.repo.exists(**kwargs)
