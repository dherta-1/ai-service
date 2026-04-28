from src.shared.base.base_entity import BaseEntity
from src.entities.question import Question
from peewee import BooleanField, CharField, ForeignKeyField, TextField


class Answer(BaseEntity):

    question = ForeignKeyField(Question, backref="answers")
    value = CharField(max_length=512)
    is_correct = BooleanField()
    explaination = TextField(null=True)  # keeping spec's spelling for DB column name

    class Meta:
        table_name = "answers"
