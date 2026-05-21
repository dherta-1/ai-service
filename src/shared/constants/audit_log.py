from enum import Enum


class ActorType(str, Enum):
    user = "user"
    admin = "admin"
    system = "system"


class EntityType(str, Enum):
    user = "user"
    document = "document"
    question = "question"
    question_group = "question_group"
    exam_instance = "exam_instance"
    exam_template = "exam_template"
    user_test_attempt = "user_test_attempt"


class ActionType(str, Enum):
    CREATE = "CREATE"
    UPDATE = "UPDATE"
    DELETE = "DELETE"
    LOGIN = "LOGIN"
    GENERATE = "GENERATE"
    QUEUE = "QUEUE"
    EXPORT = "EXPORT"
    SUBMIT = "SUBMIT"
    REPLACE = "REPLACE"
    BATCH_UPDATE = "BATCH_UPDATE"
