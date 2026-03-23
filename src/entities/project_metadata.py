from src.shared.base.base_entity import BaseEntity
from peewee import CharField, TextField


class ProjectMetadata(BaseEntity):
    """Project metadata entity"""

    name = CharField(max_length=255, null=False)
    description = TextField(null=True)
    version = CharField(max_length=50, default="1.0.0")

    class Meta:
        table_name = "project_metadata"
