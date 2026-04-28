from peewee import CharField, BooleanField, BigIntegerField, ForeignKeyField
from src.shared.base.base_entity import BaseEntity
from src.entities.user_test_attempt import UserTestAttempt


class UserTestAttemptAnswer(BaseEntity):
    attempt = ForeignKeyField(UserTestAttempt, backref="answers")
    question_id = CharField(max_length=255)  # UUID as string
    selected_answer_id = CharField(max_length=255, null=True)  # UUID as string
    is_correct = BooleanField(default=False)
    time_spent = BigIntegerField(default=0)  # milliseconds

    class Meta:
        table_name = "user_test_attempt_answers"
