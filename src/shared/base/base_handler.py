"""Base event handler for Kafka events"""

from abc import ABC, abstractmethod
from typing import Any, Dict
import logging

logger = logging.getLogger(__name__)


class BaseEventHandler(ABC):
    """Base class for all Kafka event handlers"""

    @property
    @abstractmethod
    def event_type(self) -> str:
        """Event type this handler processes (e.g., 'project.created')"""
        pass

    @property
    @abstractmethod
    def topic(self) -> str:
        """Kafka topic this handler subscribes to"""
        pass

    @abstractmethod
    def handle(self, key: str, value: Dict[str, Any]) -> None:
        """
        Handle the event

        Args:
            key: Event key
            value: Event payload as dictionary
        """
        pass

    async def handle_async(self, key: str, value: Dict[str, Any]) -> None:
        """Async version of handle (optional override)"""
        self.handle(key, value)

    def validate(self, value: Dict[str, Any]) -> bool:
        """Validate event payload - override for custom validation"""
        return True
