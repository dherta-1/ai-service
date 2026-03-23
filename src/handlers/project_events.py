"""Event handlers for project events"""

from typing import Any, Dict
from src.shared.base.base_handler import BaseEventHandler
from src.services.project_metadata_service import ProjectMetadataService
import logging

logger = logging.getLogger(__name__)


class ProjectCreatedEventHandler(BaseEventHandler):
    """Handles project.created events"""

    event_type = "project.created"
    topic = "project-events"

    def __init__(self, service: ProjectMetadataService = None):
        self.service = service or ProjectMetadataService()

    @property
    def event_type(self) -> str:
        return "project.created"

    @property
    def topic(self) -> str:
        return "project-events"

    def validate(self, value: Dict[str, Any]) -> bool:
        """Validate project creation event"""
        required_fields = {"project_id", "project_name", "timestamp"}
        return all(field in value for field in required_fields)

    def handle(self, key: str, value: Dict[str, Any]) -> None:
        """Handle project creation event"""
        try:
            if not self.validate(value):
                logger.warning(f"Invalid project.created event: {value}")
                return

            project_id = value.get("project_id")
            project_name = value.get("project_name")
            timestamp = value.get("timestamp")

            logger.info(
                f"Processing project.created event - "
                f"ID: {project_id}, Name: {project_name}, Timestamp: {timestamp}"
            )

            # You can add business logic here
            # e.g., update project status, send notifications, etc.

        except Exception as e:
            logger.error(f"Error handling project.created event: {e}", exc_info=True)


class ProjectUpdatedEventHandler(BaseEventHandler):
    """Handles project.updated events"""

    event_type = "project.updated"
    topic = "project-events"

    def __init__(self, service: ProjectMetadataService = None):
        self.service = service or ProjectMetadataService()

    @property
    def event_type(self) -> str:
        return "project.updated"

    @property
    def topic(self) -> str:
        return "project-events"

    def validate(self, value: Dict[str, Any]) -> bool:
        """Validate project update event"""
        required_fields = {"project_id", "timestamp"}
        return all(field in value for field in required_fields)

    def handle(self, key: str, value: Dict[str, Any]) -> None:
        """Handle project update event"""
        try:
            if not self.validate(value):
                logger.warning(f"Invalid project.updated event: {value}")
                return

            project_id = value.get("project_id")
            timestamp = value.get("timestamp")
            changes = value.get("changes", {})

            logger.info(
                f"Processing project.updated event - "
                f"ID: {project_id}, Timestamp: {timestamp}, Changes: {changes}"
            )

            # You can add business logic here
            # e.g., invalidate cache, trigger webhooks, etc.

        except Exception as e:
            logger.error(f"Error handling project.updated event: {e}", exc_info=True)


class ProjectDeletedEventHandler(BaseEventHandler):
    """Handles project.deleted events"""

    event_type = "project.deleted"
    topic = "project-events"

    def __init__(self, service: ProjectMetadataService = None):
        self.service = service or ProjectMetadataService()

    @property
    def event_type(self) -> str:
        return "project.deleted"

    @property
    def topic(self) -> str:
        return "project-events"

    def validate(self, value: Dict[str, Any]) -> bool:
        """Validate project deletion event"""
        required_fields = {"project_id", "timestamp"}
        return all(field in value for field in required_fields)

    def handle(self, key: str, value: Dict[str, Any]) -> None:
        """Handle project deletion event"""
        try:
            if not self.validate(value):
                logger.warning(f"Invalid project.deleted event: {value}")
                return

            project_id = value.get("project_id")
            timestamp = value.get("timestamp")

            logger.info(
                f"Processing project.deleted event - "
                f"ID: {project_id}, Timestamp: {timestamp}"
            )

            # You can add business logic here
            # e.g., cleanup resources, archive data, etc.

        except Exception as e:
            logger.error(f"Error handling project.deleted event: {e}", exc_info=True)
