import logging
from typing import List
from uuid import UUID
from fastapi import APIRouter, Depends, Body, status

from src.container import get_di_container
from src.lib.event_bus.kafka.producer import KafkaProducerImpl
from src.services.document_service import DocumentService
from src.services.core.generate_similar_questions_service import (
    GenerateSimilarQuestionsService,
)
from src.shared.constants.general import Status
from src.shared.response.response_models import create_response
from src.shared.auth_deps import get_current_user
from src.shared.response.exception_handler import NotFoundException
from src.dtos.ai.req import GenerateSimilarQuestionsRequest
from src.entities.user import User
from src.shared.constants.user import Role

logger = logging.getLogger(__name__)

router = APIRouter()


def get_document_service() -> DocumentService:
    return get_di_container().resolve(DocumentService)


def get_kafka_producer() -> KafkaProducerImpl:
    return get_di_container().resolve(KafkaProducerImpl)


def get_similar_questions_service() -> GenerateSimilarQuestionsService:
    llm_client = get_di_container().get("llm_client")
    return GenerateSimilarQuestionsService(llm_client=llm_client)


@router.post("/queue", status_code=status.HTTP_202_ACCEPTED)
async def queue_documents_for_extraction(
    document_ids: List[UUID] = Body(..., embed=True),
    doc_service: DocumentService = Depends(get_document_service),
    kafka_producer: KafkaProducerImpl = Depends(get_kafka_producer),
    current_user: User = Depends(get_current_user),
):
    """Stage 2: Queue documents for extraction (produce document_extraction_requested events).

    Takes a list of document IDs that have been uploaded via /documents/upload,
    and publishes events to start the extraction pipeline.

    Authorization: Admin can queue any document. Users can only queue their own documents.
    """
    queued = []
    errors = []

    for doc_id in document_ids:
        try:
            document = doc_service.get_by_id(doc_id)
            if not document:
                errors.append(
                    {"document_id": str(doc_id), "error": "Document not found"}
                )
                continue

            # Check authorization: admin or document owner
            if (
                current_user.role != Role.admin.value
                and document.uploaded_by_id != current_user.id
            ):
                errors.append(
                    {
                        "document_id": str(doc_id),
                        "error": "You do not have permission to queue this document",
                    }
                )
                continue

            # Still allow queuing even if document status is completed
            if document.status not in {Status.PENDING.value, Status.COMPLETED.value}:
                errors.append(
                    {
                        "document_id": str(doc_id),
                        "error": f"Document status is {document.status}, expected PENDING or COMPLETED",
                    }
                )
                continue

            # Publish extraction event
            kafka_producer.send(
                key=None,
                value={
                    "event_type": "document_extraction_requested",
                    "document_id": str(document.id),
                },
                topic="document_extraction_requested",
            )

            queued.append(str(doc_id))
            kafka_producer.flush()  # Ensure the message is sent immediately
        except Exception as e:
            errors.append({"document_id": str(doc_id), "error": str(e)})

    return create_response(
        data={"queued": queued, "errors": errors},
        message=f"Queued {len(queued)} documents for extraction",
    )


@router.post("/generate-similar-questions", status_code=status.HTTP_200_OK)
async def generate_similar_questions(
    request: GenerateSimilarQuestionsRequest,
    service: GenerateSimilarQuestionsService = Depends(get_similar_questions_service),
    current_user: User = Depends(get_current_user),
) -> dict:
    """Generate similar questions using RAG pattern.

    Takes a question_id and performs:
    1. Vector search for similar question groups
    2. Selects reference questions with lowest variant_existence_count
    3. Generates new questions via LLM (no persistence)

    Returns:
    {
        base_question: {...},
        generated_questions: [...],
        total_generated: int
    }
    """
    try:
        result = await service.generate_similar_questions(
            question_id=request.question_id,
            k=request.k,
            vector_threshold=request.vector_threshold,
        )
        return create_response(data=result, message="Generated similar questions")
    except ValueError as e:
        raise NotFoundException(str(e))
    except Exception as e:
        logger.exception("Error generating similar questions")
        raise ValueError(f"Failed to generate questions: {str(e)}")
