import logging
import signal
import sys
import json
import threading
from typing import Any
from src.lib.event_bus.kafka.consumer import KafkaConsumerImpl
from src.settings import get_settings
from src.container import initialize_di_container
from src.handlers.event_dispatcher import (
    initialize_event_handlers,
    get_event_dispatcher,
)
from src.lib.db.peewee import get_database
from src.entities.project_metadata import ProjectMetadata

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


def setup_worker_environment():
    """Setup worker environment - similar to FastAPI app startup"""
    logger.info("Setting up worker environment...")

    # Initialize DI container
    container = initialize_di_container()
    settings = get_settings()
    container.register_singleton("settings", settings)
    container.register_singleton("database", get_database())

    # Bind models to database
    db_manager = get_database()
    db_instance = db_manager.get_db()
    ProjectMetadata._meta.database = db_instance

    # Initialize event handlers
    initialize_event_handlers()

    logger.info("Worker environment initialized")


def create_event_handler(event_key: str, event_value: dict[str, Any]) -> None:
    """
    Wrapper handler that routes events to the dispatcher based on event_type

    Args:
        event_key: Kafka message key
        event_value: Deserialized event payload
    """
    try:
        # Extract event type from payload
        event_type = event_value.get("event_type")
        if not event_type:
            logger.warning(f"Received event without event_type: {event_value}")
            return

        logger.info(f"Processing event: {event_type}")

        # Dispatch to appropriate handler(s)
        dispatcher = get_event_dispatcher()
        dispatcher.dispatch(event_type, event_key, event_value)

    except Exception as e:
        logger.error(f"Error in event handler: {e}", exc_info=True)


def main():
    """Main worker entry point"""
    logger.info("Starting event consumer worker...")
    settings = get_settings()

    # Setup worker environment
    setup_worker_environment()

    # Get all topics from registered handlers
    dispatcher = get_event_dispatcher()
    topics = list(dispatcher.get_topics())

    if not topics:
        logger.warning("No topics registered with handlers. Exiting.")
        sys.exit(1)

    logger.info(f"Subscribing to topics: {topics}")

    # Initialize consumer with event dispatcher handler
    consumer = KafkaConsumerImpl(
        topics=topics,
        handler=create_event_handler,
    )

    # Create shutdown event for graceful shutdown
    shutdown_event = threading.Event()

    # Handle graceful shutdown
    def signal_handler(sig, frame):
        logger.info("Graceful shutdown initiated...")
        shutdown_event.set()
        consumer.stop()
        consumer.close()
        sys.exit(0)

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    # Start consuming
    logger.info("Starting event consumption loop...")
    consumer.start()

    # Wait for shutdown signal (cross-platform alternative to signal.pause())
    try:
        shutdown_event.wait()
    except KeyboardInterrupt:
        pass
    finally:
        logger.info("Shutting down worker...")
        consumer.stop()
        consumer.close()


if __name__ == "__main__":
    main()
