from abc import ABC, abstractmethod
from typing import Any, Optional, Callable
import json
import logging

logger = logging.getLogger(__name__)


class BaseProducer(ABC):
    """Base class for event producers"""

    def __init__(self, topic: str):
        self.topic = topic

    @abstractmethod
    def send(
        self,
        key: Optional[str],
        value: dict[str, Any],
        topic: Optional[str] = None,
        **kwargs,
    ) -> bool:
        """Send message to topic

        Args:
            key: Optional message key
            value: Message payload as dict
            topic: Optional topic override (otherwise uses configured topic)
        """
        pass

    @abstractmethod
    def close(self):
        """Close producer connection"""
        pass

    def _serialize_value(self, value: dict[str, Any]) -> str:
        """Serialize value to JSON string"""
        try:
            return json.dumps(value)
        except Exception as e:
            logger.error(f"Error serializing value: {e}")
            raise
