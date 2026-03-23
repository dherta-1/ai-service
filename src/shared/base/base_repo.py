from typing import TypeVar, Generic, List, Optional, Type, Any
from peewee import Model
from uuid import UUID

T = TypeVar("T", bound=Model)


class BaseRepo(Generic[T]):
    """Base repository class with common CRUD operations"""

    def __init__(self, model: Type[T]):
        self.model = model

    def create(self, **kwargs) -> T:
        """Create and return a new entity"""
        entity = self.model.create(**kwargs)
        return entity

    def get_by_id(self, entity_id: UUID) -> Optional[T]:
        """Get entity by ID"""
        try:
            return self.model.get_by_id(entity_id)
        except self.model.DoesNotExist:
            return None

    def get_all(self) -> List[T]:
        """Get all entities"""
        return list(self.model.select())

    def get_all_paginated(
        self, page: int = 1, page_size: int = 10
    ) -> tuple[List[T], int]:
        """Get entities with pagination"""
        offset = (page - 1) * page_size
        query = self.model.select()
        total_count = query.count()
        entities = list(query.offset(offset).limit(page_size))
        return entities, total_count

    def update(self, entity_id: UUID, **kwargs) -> Optional[T]:
        """Update entity by ID"""
        entity = self.get_by_id(entity_id)
        if entity:
            for key, value in kwargs.items():
                setattr(entity, key, value)
            entity.save()
        return entity

    def delete(self, entity_id: UUID) -> bool:
        """Delete entity by ID"""
        entity = self.get_by_id(entity_id)
        if entity:
            entity.delete_instance()
            return True
        return False

    def filter(self, **kwargs) -> List[T]:
        """Filter entities by conditions"""
        query = self.model.select()
        for key, value in kwargs.items():
            query = query.where(getattr(self.model, key) == value)
        return list(query)

    def filter_one(self, **kwargs) -> Optional[T]:
        """Filter and return first match"""
        try:
            query = self.model.select()
            for key, value in kwargs.items():
                query = query.where(getattr(self.model, key) == value)
            return query.get()
        except self.model.DoesNotExist:
            return None

    def exists(self, **kwargs) -> bool:
        """Check if entity exists"""
        return self.filter_one(**kwargs) is not None

    def count(self) -> int:
        """Get total count of entities"""
        return self.model.select().count()
