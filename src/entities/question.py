from src.shared.base.base_entity import BaseEntity
from src.entities.page import Page
from peewee import CharField, ForeignKeyField, TextField, SmallIntegerField
from playhouse.postgres_ext import BinaryJSONField
from pgvector.peewee import VectorField


class Question(BaseEntity):

    page = ForeignKeyField(Page, backref="questions")
    question_text = TextField()  # Store the question markdown text
    question_type = CharField(
        max_length=50
    )  # Store the type of question (e.g., "text", "multiple_choice", etc.)

    ## Taxonomy fields for categorization and difficulty level
    difficulty = CharField(
        max_length=50, null=True
    )  # Optional difficulty level (e.g., "easy", "medium", "hard")
    subject = CharField(
        max_length=50, null=True, index=True
    )  # Optional subject for categorization
    topic = CharField(
        max_length=50, null=True, index=True
    )  # Optional topic for further categorization (e.g., "algebra", "geometry", etc.)
    sub_questions = BinaryJSONField(
        null=True
    )  # For composite questions, store list of sub-questions as JSON string
    answers = BinaryJSONField(
        null=True
    )  # Store possible answers for multiple choice questions (as JSON string)
    correct_answer = TextField(
        null=True
    )  # Store the correct answer for the question, support both text and multiple choice, has explanation field for the correct answer

    image_list = BinaryJSONField(
        null=True
    )  # JSON string to store list of file ids (e.g., ["file_id1", "file_id2", ...])

    vector_embedding = VectorField(
        dimensions=768, null=True
    )  # Optional field to store vector embedding for the question

    status = SmallIntegerField(
        default=0
    )  # Status field for approving state (e.g., 0 = pending, 1 = approved, 2 = rejected)

    class Meta:
        collection_name = "questions"
