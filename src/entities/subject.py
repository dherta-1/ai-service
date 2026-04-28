from src.shared.base.base_entity import BaseEntity
from src.entities.document import Document
from peewee import CharField, TextField


class Subject(BaseEntity):

    name = CharField(max_length=255)
    name_vi = CharField(max_length=255, null=True)  # Vietnamese name for the subject
    code = CharField(
        max_length=50, unique=True, index=True
    )  # Unique code for the subject (e.g., "math", "physics")
    description = TextField(null=True)  # Optional description of the subject

    class Meta:
        table_name = "subjects"
