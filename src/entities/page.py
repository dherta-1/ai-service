from src.shared.base.base_entity import BaseEntity
from src.entities.document import Document
from peewee import ForeignKeyField, IntegerField, TextField, UUIDField
from playhouse.postgres_ext import BinaryJSONField


class Page(BaseEntity):

    document = ForeignKeyField(Document, backref="pages")
    page_number = IntegerField()
    content = TextField(null=True)  # Store extracted raw markdown content of the page
    validated_content = TextField(null=True)  # Store validated content after processing
    page_image_id = UUIDField(null=True)  # Store the file id of the page image (if any)
    image_list = BinaryJSONField(
        null=True
    )  # JSON string to store list of file ids (e.g., ["file_id1", "file_id2", ...])

    class Meta:
        collection_name = "pages"
