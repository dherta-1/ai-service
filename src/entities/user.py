from peewee import BooleanField, CharField, DateTimeField
from src.shared.constants.user import Role
from src.shared.base.base_entity import BaseEntity


class User(BaseEntity):
    name = CharField(max_length=255)
    email = CharField(max_length=255, unique=True)
    password_hash = CharField(max_length=255, null=True)
    role = CharField(max_length=50, default=Role.user.value)
    is_email_verified = BooleanField(default=False)
    email_verification_sent_at = DateTimeField(null=True)
    last_login_at = DateTimeField(null=True)

    class Meta:
        table_name = "users"
