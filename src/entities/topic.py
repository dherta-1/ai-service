from src.shared.base.base_entity import BaseEntity
from peewee import CharField, TextField


class Topic(BaseEntity):

    name = CharField(max_length=255)
    code = CharField(
        max_length=50, unique=True, index=True
    )  # Unique code for the topic (e.g., "algebra", "calculus")
    description = TextField(null=True)  # Optional description of the topic

    class Meta:
        collection_name = "topics"
