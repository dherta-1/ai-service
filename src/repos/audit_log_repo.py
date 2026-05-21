from __future__ import annotations

from typing import List, Optional, Tuple
from uuid import UUID

from src.entities.audit_log import AuditLog
from src.shared.base.base_repo import BaseRepo


class AuditLogRepository(BaseRepo[AuditLog]):

    def __init__(self):
        super().__init__(AuditLog)

    def get_paginated_filtered(
        self,
        page: int = 1,
        page_size: int = 20,
        actor_type: Optional[str] = None,
        actor_id: Optional[UUID] = None,
        entity_type: Optional[str] = None,
        action_type: Optional[str] = None,
    ) -> Tuple[List[AuditLog], int]:
        query = AuditLog.select()
        if actor_type:
            query = query.where(AuditLog.actor_type == actor_type)
        if actor_id:
            query = query.where(AuditLog.actor_id == actor_id)
        if entity_type:
            query = query.where(AuditLog.entity_type == entity_type)
        if action_type:
            query = query.where(AuditLog.action_type == action_type)
        total = query.count()
        offset = (page - 1) * page_size
        logs = list(query.order_by(AuditLog.created_at.desc()).offset(offset).limit(page_size))
        return logs, total
