from pydantic import BaseModel
from typing import Optional, List


class GeneratedQuestionResponse(BaseModel):
    question_text: str
    question_type: str
    difficulty: Optional[str] = None
    subject: Optional[str] = None
    topic: Optional[str] = None
    answers: Optional[List[dict]] = None
    sub_questions: Optional[List[dict]] = None
    image_list: Optional[List[str]] = None

    class Config:
        from_attributes = True


class GenerateSimilarQuestionsResponse(BaseModel):
    base_question: dict
    generated_questions: List[GeneratedQuestionResponse]
    total_generated: int

    class Config:
        from_attributes = True
