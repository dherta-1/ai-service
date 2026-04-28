from peewee import CharField, IntegerField, ForeignKeyField
from src.shared.base.base_entity import BaseEntity
from src.entities.exam_instance import ExamInstance


class ExamTestSection(BaseEntity):
    exam_instance = ForeignKeyField(ExamInstance, backref="sections")
    name = CharField(max_length=255)
    order_index = IntegerField(default=0)

    class Meta:
        table_name = "exam_test_sections"
