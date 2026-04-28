from peewee import CharField, DateTimeField
from src.shared.base.base_entity import BaseEntity


class User(BaseEntity):
    name = CharField(max_length=255)
    email = CharField(max_length=255, unique=True)
    hash_password = CharField(max_length=255)
    role = CharField(max_length=50, default="student")  # teacher | student
    reset_password_token = CharField(max_length=50, null=True)
    last_login_at = DateTimeField(null=True)

    class Meta:
        table_name = "users"
