from enum import IntEnum


class ExamInstanceStatus(IntEnum):
    PENDING = 0  # newly generated, awaiting review
    ACCEPTED = 1  # approved — can generate versions
    REJECTED = 2  # rejected — cannot generate versions


class UserTestAttemptStatus(IntEnum):
    IN_PROGRESS = 0
    SUBMITTED = 1
    EXPIRED = 2
