from src.shared.base.base_entity import BaseEntity
from src.entities.page import Page
from src.entities.question_group import QuestionGroup
from peewee import (
    CharField,
    ForeignKeyField,
    TextField,
    SmallIntegerField,
    BigIntegerField,
    IntegerField,
)
from playhouse.postgres_ext import BinaryJSONField
from pgvector.peewee import VectorField


class Question(BaseEntity):

    page = ForeignKeyField(Page, backref="questions", null=True)
    parent_question = ForeignKeyField("self", backref="sub_questions", null=True)
    questions_group = ForeignKeyField(QuestionGroup, backref="questions", null=True)

    question_text = TextField()
    question_type = CharField(max_length=50)

    # Taxonomy — null for sub-questions (parent_question != null)
    difficulty = CharField(max_length=50, null=True)
    subject = CharField(max_length=255, null=True, index=True)
    topic = CharField(max_length=255, null=True, index=True)

    # null for sub-questions
    image_list = BinaryJSONField(null=True)
    sub_question_order = IntegerField(
        null=True
    )  # Order of sub-questions if this is a parent question
    variant_existence_count = BigIntegerField(default=1)
    vector_embedding = VectorField(dimensions=768, null=True)
    status = SmallIntegerField(default=0)  # 0=pending, 1=approved, 2=rejected

    class Meta:
        table_name = "questions"
        indexes = ((("subject", "topic", "difficulty"), False),)
