from src.shared.base.base_entity import BaseEntity
from src.entities.user import User
from peewee import BigIntegerField, CharField, ForeignKeyField
from pgvector.peewee import VectorField


class QuestionGroup(BaseEntity):

    subject = CharField(max_length=255)
    topic = CharField(max_length=255)
    difficulty = CharField(max_length=50)
    existence_count = BigIntegerField(default=0)
    vector_embedding = VectorField(dimensions=768, null=True)
    from_user = ForeignKeyField(User, column_name="from_user_id", backref="question_groups", null=True, index=True)

    class Meta:
        table_name = "questions_groups"
