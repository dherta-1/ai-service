from src.shared.base.base_entity import BaseEntity
from peewee import CharField, TextField, FloatField


class Document(BaseEntity):

    name = CharField(max_length=255)
    file_id = CharField(max_length=255)
    status = CharField(max_length=50, default="pending")
    progress = FloatField(default=0.0)  # Progress percentage (0.0 to 100.0)
    metadata = TextField(null=True)  # JSON string for additional metadata

    class Meta:
        collection_name = "documents"
