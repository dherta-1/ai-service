from __future__ import annotations

import logging
from typing import Any, Dict

from src.shared.base.base_handler import BaseEventHandler
from src.services.audit_log_service import AuditLogService

logger = logging.getLogger(__name__)


class AuditLogEventHandler(BaseEventHandler):
    """Handler for audit_log_created events from Kafka"""

    def __init__(self):
        self.service = AuditLogService()

    @property
    def event_type(self) -> str:
        return "audit_log_created"

    @property
    def topic(self) -> str:
        return "audit_log_created"

    def validate(self, value: Dict[str, Any]) -> bool:
        """Validate that required audit log fields are present"""
        required_fields = {
            "event_type",
            "actor_type",
            "entity_type",
            "action_type",
        }
        return all(field in value for field in required_fields)

    def handle(self, _: str, value: Dict[str, Any]) -> None:
        """Handle incoming audit log event from Kafka"""
        try:
            logger.debug(f"Processing audit event: {value.get('event_type')}")

            if not self.validate(value):
                logger.warning(f"Invalid audit event structure: {value}")
                return

            self.service.create_log(
                actor_type=value.get("actor_type"),
                entity_type=value.get("entity_type"),
                action_type=value.get("action_type"),
                actor_id=value.get("actor_id"),
                entity_id=value.get("entity_id"),
                before_data=value.get("before_data"),
                after_data=value.get("after_data"),
                request_ip=value.get("request_ip"),
                client=value.get("client"),
            )
            logger.info(
                f"Audit log created: {value.get('actor_type')} "
                f"{value.get('action_type')} {value.get('entity_type')}"
            )
        except Exception as e:
            logger.error(f"Error processing audit event: {e}", exc_info=True)
