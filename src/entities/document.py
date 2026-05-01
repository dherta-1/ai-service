from src.shared.constants.general import Status
from src.shared.base.base_entity import BaseEntity
from src.entities.user import User
from peewee import CharField, FloatField, ForeignKeyField
from playhouse.postgres_ext import BinaryJSONField


class Document(BaseEntity):

    name = CharField(max_length=255)
    file_id = CharField(max_length=255)
    status = CharField(max_length=50, default=Status.PENDING.value)
    progress = FloatField(default=0.0)
    metadata = BinaryJSONField(null=True)
    uploaded_by = ForeignKeyField(
        User,
        column_name="uploaded_by_id",
        backref="documents",
        null=True,
        index=True,
    )

    class Meta:
        table_name = "documents"
