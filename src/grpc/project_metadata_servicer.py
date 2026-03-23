import logging
from datetime import datetime
from uuid import UUID

import grpc

from src.services.project_metadata_service import ProjectMetadataService
from src.grpc_generated.project_metadata_pb2 import (
    ProjectMetadataResponse,
    ProjectMetadataListResponse,
)
from src.grpc_generated.project_metadata_pb2_grpc import (
    ProjectMetadataServiceServicer,
)
from src.grpc_generated.common_pb2 import Empty

logger = logging.getLogger(__name__)


def datetime_to_timestamp(dt: datetime) -> tuple[int, int]:
    """Convert datetime to seconds and nanos"""
    if dt is None:
        return 0, 0
    timestamp = dt.timestamp()
    seconds = int(timestamp)
    nanos = int((timestamp - seconds) * 1e9)
    return seconds, nanos


class ProjectMetadataGrpcServicer(ProjectMetadataServiceServicer):
    """gRPC servicer for ProjectMetadata"""

    def __init__(self, service: ProjectMetadataService = None):
        self.service = service or ProjectMetadataService()

    def CreateProject(self, request, context):
        """Create a new project"""
        try:
            project = self.service.create(
                name=request.name,
                description=request.description,
                version=request.version,
            )
            created_seconds, created_nanos = datetime_to_timestamp(project.created_at)
            updated_seconds, updated_nanos = datetime_to_timestamp(project.updated_at)

            return ProjectMetadataResponse(
                id=str(project.id),
                name=project.name,
                description=project.description,
                version=project.version,
                created_at_seconds=created_seconds,
                created_at_nanos=created_nanos,
                updated_at_seconds=updated_seconds,
                updated_at_nanos=updated_nanos,
            )
        except Exception as e:
            logger.error(f"Error creating project: {e}")
            context.set_details(f"Error creating project: {e}")
            context.set_code(grpc.StatusCode.INTERNAL)
            raise

    def GetProject(self, request, context):
        """Get project by ID"""
        try:
            project = self.service.get_by_id(UUID(request.id))
            if not project:
                context.set_details(f"Project {request.id} not found")
                context.set_code(grpc.StatusCode.NOT_FOUND)
                raise Exception(f"Project {request.id} not found")

            created_seconds, created_nanos = datetime_to_timestamp(project.created_at)
            updated_seconds, updated_nanos = datetime_to_timestamp(project.updated_at)

            return ProjectMetadataResponse(
                id=str(project.id),
                name=project.name,
                description=project.description,
                version=project.version,
                created_at_seconds=created_seconds,
                created_at_nanos=created_nanos,
                updated_at_seconds=updated_seconds,
                updated_at_nanos=updated_nanos,
            )
        except Exception as e:
            logger.error(f"Error getting project: {e}")
            context.set_details(str(e))
            context.set_code(grpc.StatusCode.INTERNAL)
            raise

    def ListProjects(self, request, context):
        """List all projects"""
        try:
            projects = self.service.get_all()
            project_responses = []

            for project in projects:
                created_seconds, created_nanos = datetime_to_timestamp(
                    project.created_at
                )
                updated_seconds, updated_nanos = datetime_to_timestamp(
                    project.updated_at
                )

                project_responses.append(
                    ProjectMetadataResponse(
                        id=str(project.id),
                        name=project.name,
                        description=project.description,
                        version=project.version,
                        created_at_seconds=created_seconds,
                        created_at_nanos=created_nanos,
                        updated_at_seconds=updated_seconds,
                        updated_at_nanos=updated_nanos,
                    )
                )

            return ProjectMetadataListResponse(projects=project_responses)
        except Exception as e:
            logger.error(f"Error listing projects: {e}")
            context.set_details(f"Error listing projects: {e}")
            context.set_code(grpc.StatusCode.INTERNAL)
            raise

    def UpdateProject(self, request, context):
        """Update project"""
        try:
            project = self.service.update(
                UUID(request.id),
                name=request.name,
                description=request.description,
                version=request.version,
            )
            if not project:
                context.set_details(f"Project {request.id} not found")
                context.set_code(grpc.StatusCode.NOT_FOUND)
                raise Exception(f"Project {request.id} not found")

            created_seconds, created_nanos = datetime_to_timestamp(project.created_at)
            updated_seconds, updated_nanos = datetime_to_timestamp(project.updated_at)

            return ProjectMetadataResponse(
                id=str(project.id),
                name=project.name,
                description=project.description,
                version=project.version,
                created_at_seconds=created_seconds,
                created_at_nanos=created_nanos,
                updated_at_seconds=updated_seconds,
                updated_at_nanos=updated_nanos,
            )
        except Exception as e:
            logger.error(f"Error updating project: {e}")
            context.set_details(str(e))
            context.set_code(grpc.StatusCode.INTERNAL)
            raise

    def DeleteProject(self, request, context):
        """Delete project"""
        try:
            deleted = self.service.delete(UUID(request.id))
            if not deleted:
                context.set_details(f"Project {request.id} not found")
                context.set_code(grpc.StatusCode.NOT_FOUND)
                raise Exception(f"Project {request.id} not found")

            return Empty()
        except Exception as e:
            logger.error(f"Error deleting project: {e}")
            context.set_details(str(e))
            context.set_code(grpc.StatusCode.INTERNAL)
            raise
