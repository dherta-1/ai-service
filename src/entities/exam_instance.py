from peewee import BooleanField, CharField, ForeignKeyField, SmallIntegerField
from src.shared.base.base_entity import BaseEntity
from src.entities.exam_template import ExamTemplate
from src.entities.user import User
from src.shared.constants.exam import ExamInstanceStatus


class ExamInstance(BaseEntity):
    exam_template = ForeignKeyField(ExamTemplate, backref="instances", null=True, index=True)
    parent_exam_instance = ForeignKeyField("self", null=True, backref="variants")
    created_by = ForeignKeyField(User, column_name="created_by_id", backref="exam_instances", null=True, index=True)
    exported_file_id = CharField(max_length=255, null=True)
    exam_test_code = CharField(max_length=255, unique=True)
    is_exported = BooleanField(default=False)
    is_base = BooleanField(default=True)
    status = SmallIntegerField(default=ExamInstanceStatus.PENDING, index=True)

    class Meta:
        table_name = "exam_instances"
