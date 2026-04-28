from peewee import CharField, DecimalField, TextField, ForeignKeyField
from src.shared.base.base_entity import BaseEntity
from src.entities.user import User


class UserTestAttempt(BaseEntity):
    user = ForeignKeyField(User, backref="test_attempts")
    exam_test_id = CharField(max_length=255)  # UUID as string
    attempt_records = TextField(null=True)  # jsonb
    score = DecimalField(max_digits=3, decimal_places=2, null=True)

    class Meta:
        table_name = "user_test_attempts"
