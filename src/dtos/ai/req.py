from uuid import UUID
from pydantic import BaseModel


class GenerateSimilarQuestionsRequest(BaseModel):
    question_id: UUID
    k: int = 3
    vector_threshold: float = 0.5

    class Config:
        from_attributes = True
