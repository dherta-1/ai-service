from src.shared.base.base_entity import BaseEntity
from src.entities.document import Document
from peewee import CharField, ForeignKeyField, FloatField, IntegerField, UUIDField
from playhouse.postgres_ext import BinaryJSONField
from src.shared.constants.general import Status


class Task(BaseEntity):

    name = CharField(max_length=255, null=True)
    type = CharField(max_length=50, null=True)
    entity_id = UUIDField(null=True)
    entity_type = CharField(max_length=50, null=True)
    document = ForeignKeyField(Document, backref="tasks", null=True)
    logs = BinaryJSONField(null=True)
    status = CharField(default=Status.PENDING.value, max_length=50)
    progress = FloatField(default=0.0)
    total_pages = IntegerField(null=True)
    processed_pages = IntegerField(default=0)

    class Meta:
        table_name = "tasks"
