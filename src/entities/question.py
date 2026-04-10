from src.shared.base.base_entity import BaseEntity
from src.entities.page import Page
from peewee import CharField, ForeignKeyField, TextField


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
        max_length=255, null=True
    )  # Optional subject for categorization
    topic = CharField(
        max_length=255, null=True
    )  # Optional topic for further categorization (e.g., "algebra", "geometry", etc.)

    answers = TextField(
        null=True
    )  # Store possible answers for multiple choice questions (as JSON string)
    correct_answer = TextField(
        null=True
    )  # Store the correct answer for the question, support both text and multiple choice, has explanation field for the correct answer

    image_list = TextField(
        null=True
    )  # JSON string to store list of file ids (e.g., ["file_id1", "file_id2", ...])

    class Meta:
        collection_name = "questions"
