from peewee import CharField, DateTimeField
from src.shared.constants.user import Role
from src.shared.base.base_entity import BaseEntity


class User(BaseEntity):
    name = CharField(max_length=255)
    email = CharField(max_length=255, unique=True)
    role = CharField(
        max_length=50, default=Role.student.value
    )  # teacher | student, default=Role.student.value
    reset_password_token = CharField(max_length=50, null=True)
    is_email_verified = CharField(max_length=5, default="false")  # "true" or "false"
    last_login_at = DateTimeField(null=True)

    class Meta:
        table_name = "users"
