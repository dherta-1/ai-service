from src.shared.base.base_entity import BaseEntity
from peewee import CharField, BigIntegerField
from pgvector.peewee import VectorField


class QuestionGroup(BaseEntity):

    subject = CharField(max_length=255)
    topic = CharField(max_length=255)
    difficulty = CharField(max_length=50)
    existence_count = BigIntegerField(default=0)
    vector_embedding = VectorField(dimensions=768, null=True)

    class Meta:
        table_name = "questions_groups"
