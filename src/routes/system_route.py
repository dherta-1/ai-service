from fastapi import APIRouter, Depends, status
from uuid import UUID
from pydantic import BaseModel
from datetime import datetime
from src.services.project_metadata_service import ProjectMetadataService
from src.dtos.project_metadata import ProjectMetadataReqDTO, ProjectMetadataResDTO
from src.shared.response.response_models import create_response, ApiResponse
from src.shared.response.exception_handler import NotFoundException
from src.lib.event_bus.kafka.producer import KafkaProducerImpl
from src.container import get_di_container
import json

router = APIRouter()


def get_project_service() -> ProjectMetadataService:
    """Dependency injection for ProjectMetadataService from DI container"""
    return get_di_container().resolve(ProjectMetadataService)


def get_kafka_producer() -> "KafkaProducerImpl":
    """Get shared Kafka producer from DI container"""
    return get_di_container().resolve(KafkaProducerImpl)


@router.post(
    "/projects",
    response_model=ApiResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_project(
    req: ProjectMetadataReqDTO,
    service: ProjectMetadataService = Depends(get_project_service),
):
    """Create a new project"""
    project = service.create(
        name=req.name, description=req.description, version=req.version
    )
    return create_response(
        data=ProjectMetadataResDTO.model_validate(project),
        message="Project created successfully",
    )


@router.get("/projects/{project_id}", response_model=ApiResponse)
async def get_project(
    project_id: UUID, service: ProjectMetadataService = Depends(get_project_service)
):
    """Get project by ID"""
    project = service.get_by_id(project_id)
    if not project:
        raise NotFoundException(f"Project {project_id} not found")
    return create_response(
        data=ProjectMetadataResDTO.model_validate(project),
        message="Project retrieved successfully",
    )


@router.get("/projects", response_model=ApiResponse)
async def list_projects(service: ProjectMetadataService = Depends(get_project_service)):
    """List all projects"""
    projects = service.get_all()
    return create_response(
        data=[ProjectMetadataResDTO.model_validate(p) for p in projects],
        message=f"Retrieved {len(projects)} projects",
    )


@router.put("/projects/{project_id}", response_model=ApiResponse)
async def update_project(
    project_id: UUID,
    req: ProjectMetadataReqDTO,
    service: ProjectMetadataService = Depends(get_project_service),
):
    """Update project"""
    project = service.update(
        project_id, name=req.name, description=req.description, version=req.version
    )
    if not project:
        raise NotFoundException(f"Project {project_id} not found")
    return create_response(
        data=ProjectMetadataResDTO.model_validate(project),
        message="Project updated successfully",
    )


@router.delete("/projects/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_project(
    project_id: UUID, service: ProjectMetadataService = Depends(get_project_service)
):
    """Delete project"""
    deleted = service.delete(project_id)
    if not deleted:
        raise NotFoundException(f"Project {project_id} not found")


# Event testing endpoints


class TestEventRequest(BaseModel):
    """Test event request"""

    event_type: str
    event_data: dict


@router.post("/test/events", response_model=ApiResponse)
async def publish_test_event(req: TestEventRequest):
    """Publish a test event to Kafka"""
    try:
        # Determine topic based on event type
        topic = (
            "project-events" if req.event_type.startswith("project.") else "test-events"
        )

        event_payload = {
            **req.event_data,
            "timestamp": datetime.utcnow().isoformat(),
        }

        # Use shared Kafka producer from DI container
        producer = get_kafka_producer()

        # Send event (override topic if needed)
        producer.send(
            key=req.event_data.get("project_id", "test-key"),
            value=event_payload,
            topic=topic,
        )

        return create_response(
            data={
                "event_type": req.event_type,
                "topic": topic,
                "timestamp": datetime.utcnow().isoformat(),
            },
            message=f"Event '{req.event_type}' published successfully",
        )
    except Exception as e:
        from src.shared.response.exception_handler import BadRequestException

        raise BadRequestException(f"Failed to publish event: {str(e)}")


@router.get("/test/events/demo", response_model=ApiResponse)
async def publish_demo_event():
    """Publish a demo project event for testing"""
    from uuid import uuid4

    try:
        project_id = str(uuid4())
        event_payload = {
            "event_type": "project.created",
            "project_id": project_id,
            "project_name": f"Demo Project {project_id[:8]}",
            "timestamp": datetime.utcnow().isoformat(),
        }

        # Use shared Kafka producer from DI container
        producer = get_kafka_producer()

        producer.send(
            key=project_id,
            value=event_payload,
            topic="project-events",
        )

        return create_response(
            data=event_payload,
            message="Demo event published successfully - check worker logs",
        )
    except Exception as e:
        from src.shared.response.exception_handler import BadRequestException

        raise BadRequestException(f"Failed to publish demo event: {str(e)}")


@router.get("/test/handlers/status", response_model=ApiResponse)
async def get_handlers_status():
    """Get status of registered event handlers"""
    from src.handlers.event_dispatcher import get_event_dispatcher

    dispatcher = get_event_dispatcher()
    topics = dispatcher.get_topics()

    handlers_info = {}
    for topic in topics:
        handlers = dispatcher.get_handlers_for_topic(topic)
        handlers_info[topic] = [
            {
                "handler": h.__class__.__name__,
                "event_type": h.event_type,
            }
            for h in handlers
        ]

    return create_response(
        data={
            "total_handlers": sum(len(h) for h in dispatcher.handlers.values()),
            "topics": list(topics),
            "handlers_by_topic": handlers_info,
        },
        message="Event handlers status",
    )
