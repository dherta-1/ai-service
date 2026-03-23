"""Event dispatcher for routing Kafka events to handlers"""

from typing import Dict, List, Any, Callable
from src.shared.base.base_handler import BaseEventHandler
import logging

logger = logging.getLogger(__name__)


class EventDispatcher:
    """Routes events to appropriate handlers based on event type"""

    def __init__(self):
        self.handlers: Dict[str, List[BaseEventHandler]] = {}
        self.wildcard_handlers: List[BaseEventHandler] = []

    def register_handler(self, handler: BaseEventHandler) -> None:
        """Register an event handler"""
        event_type = handler.event_type

        if event_type not in self.handlers:
            self.handlers[event_type] = []

        self.handlers[event_type].append(handler)
        logger.info(
            f"Registered handler for event type: {event_type} "
            f"(topic: {handler.topic})"
        )

    def register_wildcard_handler(self, handler: BaseEventHandler) -> None:
        """Register a handler for all events"""
        self.wildcard_handlers.append(handler)
        logger.info(f"Registered wildcard handler for all events")

    def dispatch(self, event_type: str, key: str, value: Dict[str, Any]) -> None:
        """
        Dispatch event to registered handlers

        Args:
            event_type: Type of event (e.g., 'project.created')
            key: Event key
            value: Event payload
        """
        handlers: List[BaseEventHandler] = []

        # Get specific handlers for this event type
        if event_type in self.handlers:
            handlers.extend(self.handlers[event_type])

        # Add wildcard handlers
        handlers.extend(self.wildcard_handlers)

        if not handlers:
            logger.warning(f"No handlers registered for event type: {event_type}")
            return

        logger.info(f"Dispatching event: {event_type} to {len(handlers)} handler(s)")

        for handler in handlers:
            try:
                handler.handle(key, value)
            except Exception as e:
                logger.error(
                    f"Error in handler {handler.__class__.__name__}: {e}",
                    exc_info=True,
                )

    def get_topics(self) -> set[str]:
        """Get all topics that have registered handlers"""
        topics = set()
        for handler_list in self.handlers.values():
            for handler in handler_list:
                topics.add(handler.topic)

        for handler in self.wildcard_handlers:
            topics.add(handler.topic)

        return topics

    def get_handlers_for_topic(self, topic: str) -> List[BaseEventHandler]:
        """Get all handlers for a specific topic"""
        topic_handlers = []
        for handler_list in self.handlers.values():
            topic_handlers.extend([h for h in handler_list if h.topic == topic])

        topic_handlers.extend([h for h in self.wildcard_handlers if h.topic == topic])
        return topic_handlers


# Global event dispatcher instance
_dispatcher: EventDispatcher | None = None


def get_event_dispatcher() -> EventDispatcher:
    """Get or create the global event dispatcher"""
    global _dispatcher
    if _dispatcher is None:
        _dispatcher = EventDispatcher()
    return _dispatcher


def initialize_event_handlers() -> None:
    """Initialize all event handlers"""
    from src.handlers.project_events import (
        ProjectCreatedEventHandler,
        ProjectUpdatedEventHandler,
        ProjectDeletedEventHandler,
    )

    dispatcher = get_event_dispatcher()

    # Register project event handlers
    dispatcher.register_handler(ProjectCreatedEventHandler())
    dispatcher.register_handler(ProjectUpdatedEventHandler())
    dispatcher.register_handler(ProjectDeletedEventHandler())

    logger.info(f"Event handlers initialized - Topics: {dispatcher.get_topics()}")
