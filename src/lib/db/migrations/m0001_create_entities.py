"""
Migration m0001_create_entities: Create core document entity tables
"""

from src.lib.db.peewee import get_database
from src.entities.subject import Subject
from src.entities.topic import Topic
from src.shared.base.base_migration import BaseMigration
from src.entities.document import Document
from src.entities.file_metadata import FileMetadata
from src.entities.page import Page
from src.entities.question import Question
from src.entities.task import Task


class MigrationCreateEntities(BaseMigration):
    """Create core document-related tables"""

    def up(self):
        db_instance = self.db.get_db()
        db_instance.execute_sql(
            "CREATE EXTENSION IF NOT EXISTS vector;"
        )  # Ensure pgvector extension is available
        Document._meta.database = db_instance
        FileMetadata._meta.database = db_instance
        Page._meta.database = db_instance
        Question._meta.database = db_instance
        Task._meta.database = db_instance
        Subject._meta.database = db_instance
        Topic._meta.database = db_instance

        db_instance.create_tables(
            [Document, FileMetadata, Page, Question, Task, Subject, Topic]
        )

    def down(self):
        db_instance = self.db.get_db()

        Document._meta.database = db_instance
        FileMetadata._meta.database = db_instance
        Page._meta.database = db_instance
        Question._meta.database = db_instance
        Task._meta.database = db_instance
        Subject._meta.database = db_instance
        Topic._meta.database = db_instance

        db_instance.drop_tables(
            [Question, Task, Page, FileMetadata, Document, Subject, Topic]
        )
