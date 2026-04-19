from src.shared.constants.general import Status
from src.shared.base.base_entity import BaseEntity
from peewee import CharField, TextField, FloatField
from playhouse.postgres_ext import BinaryJSONField


class Document(BaseEntity):

    name = CharField(max_length=255)
    file_id = CharField(max_length=255)
    status = CharField(
        max_length=50, default=Status.PENDING.value
    )  # Use string value of Status enum
    progress = FloatField(default=0.0)  # Progress percentage (0.0 to 100.0)
    metadata = BinaryJSONField(null=True)  # JSON string for additional metadata

    class Meta:
        collection_name = "documents"
