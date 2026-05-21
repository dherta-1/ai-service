from __future__ import annotations

import json
from typing import Any, Dict, List, Optional, Tuple
from uuid import UUID

from src.entities.audit_log import AuditLog
from src.repos.audit_log_repo import AuditLogRepository
from src.shared.base.base_service import BaseService


class AuditLogService(BaseService):

    def __init__(self):
        super().__init__(AuditLogRepository())

    def create_log(
        self,
        actor_type: str,
        entity_type: str,
        action_type: str,
        actor_id: Optional[UUID] = None,
        entity_id: Optional[UUID] = None,
        before_data: Optional[Dict[str, Any]] = None,
        after_data: Optional[Dict[str, Any]] = None,
        request_ip: Optional[str] = None,
        client: Optional[str] = None,
    ) -> AuditLog:
        return self.repo.create(
            actor_type=actor_type,
            actor_id=actor_id,
            entity_type=entity_type,
            entity_id=entity_id,
            action_type=action_type,
            before_data=json.dumps(before_data) if before_data is not None else None,
            after_data=json.dumps(after_data) if after_data is not None else None,
            request_ip=request_ip,
            client=client,
        )

    def list_logs(
        self,
        page: int = 1,
        page_size: int = 20,
        actor_type: Optional[str] = None,
        actor_id: Optional[UUID] = None,
        entity_type: Optional[str] = None,
        action_type: Optional[str] = None,
    ) -> Tuple[List[AuditLog], int]:
        return self.repo.get_paginated_filtered(
            page=page,
            page_size=page_size,
            actor_type=actor_type,
            actor_id=actor_id,
            entity_type=entity_type,
            action_type=action_type,
        )
