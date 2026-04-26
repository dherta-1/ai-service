from src.shared.base.base_entity import BaseEntity
from src.entities.document import Document
from peewee import (
    BooleanField,
    CharField,
    ForeignKeyField,
    TextField,
)
from playhouse.postgres_ext import BinaryJSONField
from src.entities.question import Question


class Answer(BaseEntity):

    questions = ForeignKeyField(Question, backref="answers")
    value = CharField(
        max_length=512, null=True
    )  # Store the answer text (for text questions) or the selected option (for multiple choice)
    is_correct = BooleanField(
        null=True
    )  # Store whether the answer is correct (1 for correct, 0 for incorrect), useful for multiple choice questions
    explanation = TextField(
        null=True
    )  # Optional field to store explanation for the answer, can be used for both text and multiple choice questions

    class Meta:
        collection_name = "answers"
