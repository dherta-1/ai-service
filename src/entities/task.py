from src.shared.base.base_entity import BaseEntity
from src.entities.document import Document
from peewee import ForeignKeyField, TextField, FloatField


class Task(BaseEntity):

    document = ForeignKeyField(Document, backref="tasks")
    logs = TextField(null=True)  # Store logs or progress information
    progress = FloatField(default=0.0)  # Progress percentage (0.0 to 100.0)
    status = TextField(
        default="pending"
    )  # Task status (e.g., pending, in_progress, completed, failed)

    class Meta:
        collection_name = "tasks"
