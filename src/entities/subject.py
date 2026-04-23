from src.shared.base.base_entity import BaseEntity
from src.entities.document import Document
from peewee import CharField, TextField


class Subject(BaseEntity):

    name = CharField(max_length=255)
    code = CharField(
        max_length=50, unique=True, index=True
    )  # Unique code for the subject (e.g., "math", "physics")
    description = TextField(null=True)  # Optional description of the subject

    class Meta:
        collection_name = "subjects"
