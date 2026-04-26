from enum import Enum


class QuestionType(str, Enum):
    MULTIPLE_CHOICE = "multiple_choice"
    TRUE_FALSE = "true_false"
    SHORT_ANSWER = "short_answer"
    ESSAY = "essay"
    SELECTION = "selection"  # For questions that has more than one correct answer, but not necessarily all options are correct (e.g., "select all that apply")
    COMPOSITE = (
        "composite"  # For questions that have multiple sub-questions of different types
    )


class DifficultyLevel(str, Enum):
    EASY = "easy"
    MEDIUM = "medium"
    HARD = "hard"


class Subject(str, Enum):
    MATH = "math"
    SCIENCE = "science"
    HISTORY = "history"
    LITERATURE = "literature"
