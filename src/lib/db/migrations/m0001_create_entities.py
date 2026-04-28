"""
Migration m0001_create_entities: Create all core entity tables
"""

from src.lib.db.peewee import get_database
from src.shared.base.base_migration import BaseMigration

# Common/General tables
from src.entities.user import User
from src.entities.file_metadata import FileMetadata
from src.entities.subject import Subject
from src.entities.topic import Topic
from src.entities.task import Task

# Document group tables
from src.entities.document import Document
from src.entities.page import Page
from src.entities.question_group import QuestionGroup
from src.entities.question import Question
from src.entities.answer import Answer

# Exam/Test group tables
from src.entities.user_test_attempt import UserTestAttempt
from src.entities.user_test_attempt_answer import UserTestAttemptAnswer
from src.entities.exam_template import ExamTemplate
from src.entities.exam_instance import ExamInstance
from src.entities.exam_test_section import ExamTestSection
from src.entities.question_exam_test import QuestionExamTest


class MigrationCreateEntities(BaseMigration):
    """Create all core entity tables"""

    def up(self):
        db_instance = self.db.get_db()

        # Enable pgvector extension for vector embeddings
        db_instance.execute_sql("CREATE EXTENSION IF NOT EXISTS vector;")

        # Bind all models to database instance
        models = [
            # Common/General
            User,
            FileMetadata,
            Subject,
            Topic,
            Task,
            # Document group
            Document,
            Page,
            QuestionGroup,
            Question,
            Answer,
            # Exam/Test group
            UserTestAttempt,
            UserTestAttemptAnswer,
            ExamTemplate,
            ExamInstance,
            ExamTestSection,
            QuestionExamTest,
        ]

        for model in models:
            model._meta.database = db_instance

        # Create tables in dependency order
        db_instance.create_tables(
            [
                # Common/General (no dependencies)
                User,
                FileMetadata,
                Subject,
                Topic,
                Task,
                # Document group
                Document,
                Page,
                QuestionGroup,
                Question,
                Answer,
                # Exam/Test group (depends on User, Question, ExamTemplate)
                UserTestAttempt,
                UserTestAttemptAnswer,
                ExamTemplate,
                ExamInstance,
                ExamTestSection,
                QuestionExamTest,
            ]
        )

    def down(self):
        db_instance = self.db.get_db()

        # Bind all models
        models = [
            User,
            FileMetadata,
            Subject,
            Topic,
            Task,
            Document,
            Page,
            QuestionGroup,
            Question,
            Answer,
            UserTestAttempt,
            UserTestAttemptAnswer,
            ExamTemplate,
            ExamInstance,
            ExamTestSection,
            QuestionExamTest,
        ]

        for model in models:
            model._meta.database = db_instance

        # Drop tables in reverse dependency order
        db_instance.drop_tables(
            [
                # Exam/Test group (dropped first due to dependencies)
                QuestionExamTest,
                ExamTestSection,
                ExamInstance,
                ExamTemplate,
                UserTestAttemptAnswer,
                UserTestAttempt,
                # Document group
                Answer,
                Question,
                QuestionGroup,
                Page,
                Document,
                # Common/General
                Task,
                Topic,
                Subject,
                FileMetadata,
                User,
            ]
        )
