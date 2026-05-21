from peewee import CharField, TextField, UUIDField
from src.shared.base.base_entity import BaseEntity


class AuditLog(BaseEntity):
    actor_type = CharField(max_length=50)  # user | admin
    actor_id = UUIDField(null=True)
    entity_type = CharField(max_length=100)
    entity_id = UUIDField(null=True)
    action_type = CharField(max_length=50)  # CREATE | UPDATE | DELETE | LOGIN
    before_data = TextField(null=True)
    after_data = TextField(null=True)
    request_ip = CharField(max_length=100, null=True)
    client = CharField(max_length=255, null=True)

    class Meta:
        table_name = "audit_logs"
