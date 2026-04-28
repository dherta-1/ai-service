from abc import ABC, abstractmethod
from typing import Callable, Optional, Any
import json
import logging

logger = logging.getLogger(__name__)


class BaseConsumer(ABC):
    """Base class for event consumers"""

    def __init__(
        self, topics: list[str], handler: Callable[[str, dict[str, Any]], None]
    ):
        self.topics = topics
        self.handler = handler

    @abstractmethod
    def start(self):
        """Start consuming messages"""
        pass

    @abstractmethod
    def stop(self):
        """Stop consuming messages"""
        pass

    @abstractmethod
    def close(self):
        """Close consumer connection"""
        pass

    def _deserialize_value(self, value: str) -> dict[str, Any]:
        """Deserialize JSON string to dict"""
        try:
            return json.loads(value)
        except Exception as e:
            logger.error(f"Error deserializing value: {e}")
            raise

    def _handle_message(self, key: Optional[str], value: str):
        """Handle incoming message"""
        try:
            deserialized_value = self._deserialize_value(value)
            self.handler(key, deserialized_value)
        except Exception as e:
            logger.error(f"Error handling message: {e}")
