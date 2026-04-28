from src.shared.base.base_entity import BaseEntity
from peewee import CharField, TextField


class Topic(BaseEntity):

    name = CharField(max_length=255)
    name_vi = CharField(max_length=255, null=True)  # Vietnamese name for the topic
    code = CharField(
        max_length=50, unique=True, index=True
    )  # Unique code for the topic (e.g., "algebra", "calculus")
    description = TextField(null=True)  # Optional description of the topic

    class Meta:
        table_name = "topics"
