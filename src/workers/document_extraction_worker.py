"""Document extraction separated event worker.

Consumes only document-extraction related events:
- document_extraction_requested → OCR + validate → emit question_extraction_requested per page
"""

import logging
import signal
import sys
import threading
from src.lib.event_bus.kafka.producer import KafkaProducerImpl
from src.lib.cachedb.redis import get_cache_client
from src.lib.s3_client import get_s3_client
from src.llm.base import LLMConfig
from src.llm.registry import register_llm_registry
from src.ocr.base import OCRConfig
from src.ocr.registry import register_ocr_registry
from src.settings import get_settings
from src.container import initialize_di_container
from src.lib.db.peewee import get_database
from src.lib.event_bus.kafka.consumer import KafkaConsumerImpl
from src.entities.document import Document
from src.entities.file_metadata import FileMetadata
from src.entities.page import Page
from src.entities.question import Question
from src.entities.question_group import QuestionGroup
from src.entities.answer import Answer
from src.entities.subject import Subject
from src.entities.task import Task
from src.entities.topic import Topic
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
    models = [
        Document,
        FileMetadata,
        Page,
        Question,
        QuestionGroup,
        Answer,
        Subject,
        Task,
        Topic,
    ]
    for model in models:
        model._meta.database = db_instance


def setup_document_extraction_worker_environment() -> None:
    """Setup DI + document-extraction profile handlers."""
    logger.info("Setting up document extraction worker environment...")
    container = initialize_di_container()
    settings = get_settings()

    # Register singletons
    container.register_singleton("settings", settings)
    container.register_singleton("database", get_database())
    container.register_singleton("cache", get_cache_client())
    s3_client = get_s3_client(settings)
    container.register_singleton("s3_client", s3_client)

    # ensure S3 bucket if configured
    s3_bucket = getattr(settings, "aws_s3_bucket", None)
    container.register_singleton("s3_bucket", s3_bucket)
    if s3_bucket:
        try:
            s3_client.ensure_bucket(s3_bucket, region_name=settings.aws_region)
        except Exception as e:
            logger.warning("Unable to ensure S3 bucket '%s' exists: %s", s3_bucket, e)

    # Register llm registry in DI and default llm client (if configured)
    llm_registry = register_llm_registry(container)

    llm_conf = LLMConfig(
        provider=settings.llm_provider,
        api_key=settings.llm_api_key,
        model=settings.llm_model,
        embedding_model=settings.llm_embedding_model,
        embedding_dimension=settings.llm_embedding_dimension,
        host=settings.llm_host,
        use_vertex_ai=settings.llm_use_vertex_ai,
        vertex_project=settings.llm_vertex_project,
        vertex_location=settings.llm_vertex_location,
    )

    try:
        llm_client = llm_registry.create_client(llm_conf, client_id="default_llm")
        container.register_singleton("llm_client", llm_client)
    except Exception as e:
        logger.warning("Could not create LLm client at startup: %s", e)
        container.register_singleton("llm_client", None)

    # Register OCR registry in DI and default OCR client (if configured)
    ocr_registry = register_ocr_registry(container)
    ocr_conf = OCRConfig(
        provider=settings.ocr_provider,
        lang=settings.ocr_lang,
        use_gpu=settings.ocr_use_gpu,
    )

    try:
        ocr_client = ocr_registry.create_client(ocr_conf, client_id="default_ocr")
        container.register_singleton("ocr_client", ocr_client)
    except Exception as e:
        logger.warning("Could not create OCR client at startup: %s", e)

    kafka_producer = KafkaProducerImpl(topic="question_extraction_requested")
    container.register_singleton("kafka_producer", kafka_producer)

    _bind_models_to_database()

    initialize_event_handlers_by_profile("document-extraction")

    logger.info("Document extraction worker environment initialized")


def main():
    """Main document extraction separated event worker entry point."""
    logger.info("Starting document extraction worker service...")
    setup_document_extraction_worker_environment()

    dispatcher = get_event_dispatcher()
    topics = list(dispatcher.get_topics())
    consumer = KafkaConsumerImpl(
        topics=topics,
        handler=lambda key, value: dispatcher.dispatch(
            value.get("event_type", ""), key, value
        ),
    )

    shutdown_event = threading.Event()

    def signal_handler(sig, frame):
        logger.info("Graceful shutdown initiated...")
        shutdown_event.set()
        consumer.stop()
        consumer.close()
        sys.exit(0)

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    try:
        logger.info("Document extraction event worker is running on topics: %s", topics)
        consumer.start()
        shutdown_event.wait()
    except KeyboardInterrupt:
        pass
    finally:
        logger.info("Shutting down document extraction event worker...")
        consumer.stop()
        consumer.close()
        logger.info("Document extraction event worker stopped")


if __name__ == "__main__":
    main()
