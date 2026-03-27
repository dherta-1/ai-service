from fastapi import APIRouter, Depends, status
from uuid import UUID
from pydantic import BaseModel
from datetime import datetime
from src.services.project_metadata_service import ProjectMetadataService
from src.dtos.project_metadata import ProjectMetadataReqDTO, ProjectMetadataResDTO
from src.shared.response.response_models import create_response, ApiResponse
from src.shared.response.exception_handler import NotFoundException
from src.container import get_di_container
import json

router = APIRouter()


def get_project_service() -> ProjectMetadataService:
    """Dependency injection for ProjectMetadataService from DI container"""
    return get_di_container().resolve(ProjectMetadataService)


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
