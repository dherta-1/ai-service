from peewee import CharField, TextField
from src.shared.base.base_entity import BaseEntity


class ExamTemplate(BaseEntity):
    name = CharField(max_length=255)
    subject = CharField(max_length=50)
    generation_config = TextField(null=True)  # jsonb

    class Meta:
        table_name = "exam_templates"
