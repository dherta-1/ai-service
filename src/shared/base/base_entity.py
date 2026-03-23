from peewee import Model, UUIDField, DateTimeField
from uuid import uuid4
from datetime import datetime


class BaseEntity(Model):
    """Base model for all Peewee entities with UUID primary key and timestamps"""

    id = UUIDField(primary_key=True, default=uuid4)
    created_at = DateTimeField(default=datetime.utcnow, index=True)
    updated_at = DateTimeField(default=datetime.utcnow)

    def save(self, *args, **kwargs):
        """Override save to update the updated_at timestamp"""
        self.updated_at = datetime.utcnow()
        return super().save(*args, **kwargs)

    class Meta:
        abstract = True
