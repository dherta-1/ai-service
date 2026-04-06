from src.shared.base.base_entity import BaseEntity
from peewee import CharField, BigIntegerField


class FileMetadata(BaseEntity):

    name = CharField(max_length=255)
    path = CharField(max_length=1024)
    size = BigIntegerField(default=0)
    mime_type = CharField(max_length=255, null=True)
    object_key = CharField(max_length=255, null=True)

    class Meta:
        collection_name = "file_metadata"
