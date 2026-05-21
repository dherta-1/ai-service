"""Audit log separated event worker.

Consumes only audit-log related events:
- audit_log_created → parse and persist to database via AuditLogService
"""

import logging
import signal
import sys
import threading

from src.settings import get_settings
from src.container import initialize_di_container
from src.lib.db.peewee import get_database
from src.lib.cachedb.redis import get_cache_client
from src.lib.event_bus.kafka.consumer import KafkaConsumerImpl
from src.entities.audit_log import AuditLog
from src.handlers.event_dispatcher import (
    initialize_event_handlers_by_profile,
    get_event_dispatcher,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


def _bind_models_to_database() -> None:
    db_instance = get_database().get_db()
    models = [AuditLog]
    for model in models:
        model._meta.database = db_instance


def setup_audit_log_worker_environment() -> None:
    """Setup DI + audit-log profile handlers."""
    logger.info("Setting up audit log worker environment...")
    container = initialize_di_container()
    settings = get_settings()

    # Register singletons
    container.register_singleton("settings", settings)
    container.register_singleton("database", get_database())
    container.register_singleton("cache", get_cache_client())

    _bind_models_to_database()

    initialize_event_handlers_by_profile("audit-log")

    logger.info("Audit log worker environment initialized")


def main():
    """Main audit log separated event worker entry point."""
    logger.info("Starting audit log worker service...")
    setup_audit_log_worker_environment()

    dispatcher = get_event_dispatcher()
    topics = list(dispatcher.get_topics())
    consumer = KafkaConsumerImpl(
        topics=topics,
        handler=lambda key, value: dispatcher.dispatch(
            value.get("event_type", ""), key, value
        ),
    )

    shutdown_event = threading.Event()

    def signal_handler(_sig, _frame):
        logger.info("Graceful shutdown initiated...")
        shutdown_event.set()
        consumer.stop()
        consumer.close()
        sys.exit(0)

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    try:
        logger.info("Audit log event worker is running on topics: %s", topics)
        consumer.start()
        shutdown_event.wait()
    except KeyboardInterrupt:
        pass
    finally:
        logger.info("Shutting down audit log event worker...")
        consumer.stop()
        consumer.close()
        logger.info("Audit log event worker stopped")


if __name__ == "__main__":
    main()
