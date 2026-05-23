from datetime import datetime

from peewee import (
    CharField,
    DecimalField,
    DateTimeField,
    ForeignKeyField,
    SmallIntegerField,
)
from src.shared.base.base_entity import BaseEntity
from src.entities.exam_instance import ExamInstance
from src.entities.user import User
from src.shared.constants.exam import UserTestAttemptStatus


class UserTestAttempt(BaseEntity):
    user = ForeignKeyField(User, backref="test_attempts")
    exam_template_id = CharField(max_length=255, null=True)  # UUID as string
    exam_instance = ForeignKeyField(ExamInstance, backref="attempts", null=True)
    score = DecimalField(max_digits=5, decimal_places=2, null=True)
    status = SmallIntegerField(default=UserTestAttemptStatus.IN_PROGRESS, index=True)
    started_at = DateTimeField(default=datetime.utcnow)
    submitted_at = DateTimeField(null=True)

    class Meta:
        table_name = "user_test_attempts"
