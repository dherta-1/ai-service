from peewee import CharField, BooleanField, ForeignKeyField
from src.shared.base.base_entity import BaseEntity
from src.entities.exam_template import ExamTemplate


class ExamInstance(BaseEntity):
    exam_template = ForeignKeyField(ExamTemplate, backref="instances")
    parent_exam_instance = ForeignKeyField("self", null=True, backref="variants")
    exported_file_id = CharField(max_length=255, null=True)  # UUID as string
    exam_test_code = CharField(max_length=255, unique=True)
    is_exported = BooleanField(default=False)

    class Meta:
        table_name = "exam_instances"
