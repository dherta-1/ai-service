from __future__ import annotations

import logging
from typing import Any, Dict, Optional
from uuid import UUID

from src.shared.constants.audit_log import ActionType, ActorType, EntityType

logger = logging.getLogger(__name__)


def _get_kafka_producer():
    from src.container import get_di_container

    try:
        return get_di_container().get("kafka_producer")
    except Exception:
        return None


def log_audit(
    actor_type: ActorType | str,
    entity_type: EntityType | str,
    action_type: ActionType | str,
    actor_id: Optional[UUID] = None,
    entity_id: Optional[UUID] = None,
    before_data: Optional[Dict[str, Any]] = None,
    after_data: Optional[Dict[str, Any]] = None,
    request_ip: Optional[str] = None,
    client: Optional[str] = None,
) -> None:
    """Fire-and-forget audit log via Kafka. Silently swallows errors."""
    producer = _get_kafka_producer()
    if producer is None:
        logger.warning("Kafka producer not available, audit log skipped")
        return

    try:
        event = {
            "event_type": "audit_log_created",
            "actor_type": (
                actor_type if isinstance(actor_type, str) else actor_type.value
            ),
            "entity_type": (
                entity_type if isinstance(entity_type, str) else entity_type.value
            ),
            "action_type": (
                action_type if isinstance(action_type, str) else action_type.value
            ),
            "actor_id": str(actor_id) if actor_id else None,
            "entity_id": str(entity_id) if entity_id else None,
            "before_data": before_data,
            "after_data": after_data,
            "request_ip": request_ip,
            "client": client,
        }

        producer.send(
            key=str(entity_id) if entity_id else None,
            value=event,
            topic="audit_log_created",
        )
        producer.poll(0)
    except Exception as e:
        logger.warning("Audit log event send failed: %s", e)
