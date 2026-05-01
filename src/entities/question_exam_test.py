from peewee import CharField, IntegerField, ForeignKeyField, TextField
from src.shared.base.base_entity import BaseEntity
from src.entities.question_group import QuestionGroup
from src.entities.exam_test_section import ExamTestSection


class QuestionExamTest(BaseEntity):
    question_group = ForeignKeyField(QuestionGroup, backref="exam_tests")
    question_id = CharField(max_length=255)  # UUID as string
    exam_test_section = ForeignKeyField(ExamTestSection, backref="questions")
    order_count = IntegerField(default=0)
    answer_order = TextField(null=True)  # JSON-encoded list of shuffled answer indices e.g. "[2,0,3,1]"

    class Meta:
        table_name = "question_exam_tests"
