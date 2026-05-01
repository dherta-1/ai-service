from peewee import CharField, ForeignKeyField, TextField
from src.entities.user import User
from src.shared.base.base_entity import BaseEntity


class ExamTemplate(BaseEntity):
    name = CharField(max_length=255)
    subject = CharField(max_length=50)
    generation_config = TextField(null=True)
    created_by = ForeignKeyField(
        User,
        column_name="created_by_id",
        backref="exam_templates",
        null=True,
        index=True,
    )

    class Meta:
        table_name = "exam_templates"
