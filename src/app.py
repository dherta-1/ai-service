from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from src.repos.document_repo import DocumentRepository
from src.repos.file_metadata_repo import FileMetadataRepository
from src.repos.page_repo import PageRepository
from src.repos.question_repo import QuestionRepository
from src.repos.question_group_repo import QuestionGroupRepository
from src.repos.answer_repo import AnswerRepository
from src.repos.subject_repo import SubjectRepository
from src.repos.topic_repo import TopicRepository
from src.repos.task_repo import TaskRepository
from src.settings import get_settings
from src.container import get_di_container, initialize_di_container
from src.lib.db.peewee import get_database
from src.lib.db.migration_manager import get_migration_manager
from src.lib.db.seed_manager import get_seed_manager
from src.lib.cachedb.redis import get_cache_client
from src.lib.s3_client import get_s3_client
from src.lib.event_bus.kafka.producer import KafkaProducerImpl
from src.lib.event_bus.kafka.consumer import KafkaConsumerImpl
from src.llm.registry import get_llm_registry, register_llm_registry
from src.llm.base import LLMConfig
from src.ocr.registry import register_ocr_registry
from src.ocr.base import OCRConfig
from src.lib.grpc_server import get_grpc_server_manager
from src.routes.ai_route import router as ai_router
from src.routes.document_route import router as document_router
from src.routes.page_route import router as page_router
from src.routes.question_route import router as question_router
from src.shared.response.exception_handler import register_exception_handlers
from src.shared.response.response_models import create_response

# from src.services.document_processing_service import DocumentProcessingService
from src.services.document_service import DocumentService
from src.services.question_service import QuestionService
from src.services.page_service import PageService
from src.services.core.document_extraction_service import DocumentExtractionService
from src.services.core.question_extraction_service import QuestionExtractionService
import logging
from src.entities.document import Document
from src.entities.file_metadata import FileMetadata
from src.entities.page import Page
from src.entities.question import Question
from src.entities.question_group import QuestionGroup
from src.entities.answer import Answer
from src.entities.subject import Subject
from src.entities.task import Task
from src.entities.topic import Topic

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


def setup_di_container() -> None:
    """Setup dependency injection container"""
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
    # ocr_registry = register_ocr_registry(container)
    # ocr_conf = OCRConfig(
    #     provider=settings.ocr_provider,
    #     lang=settings.ocr_lang,
    #     use_gpu=settings.ocr_use_gpu,
    # )

    # try:
    #     ocr_client = ocr_registry.create_client(ocr_conf, client_id="default_ocr")
    #     container.register_singleton("ocr_client", ocr_client)
    # except Exception as e:
    #     logger.warning("Could not create OCR client at startup: %s", e)

    # Register Kafka producer and consumer
    kafka_producer = KafkaProducerImpl(topic="document_extraction_requested")
    container.register_singleton("kafka_producer", kafka_producer)

    # Register document processing service with DI dependencies
    # container.register_type(
    #     DocumentProcessingService,
    #     lambda: DocumentProcessingService(
    #         ocr_client=container.get("ocr_client"),
    #         s3_client=container.get("s3_client"),
    #         llm_client=container.get("llm_client"),
    #         s3_bucket=s3_bucket,
    #     ),
    #     singleton=False,
    # )

    # Register core services as singletons
    container.register_singleton("document_service", DocumentService())
    container.register_singleton("question_service", QuestionService())
    container.register_singleton("page_service", PageService())

    # Register core extraction services as factories (non-singleton)
    container.register_type(
        DocumentExtractionService,
        lambda: DocumentExtractionService(
            llm_client=container.get("llm_client"),
            ocr_client=container.get("ocr_client"),
            s3_client=container.get("s3_client"),
            s3_bucket=s3_bucket,
        ),
        singleton=False,
    )

    container.register_type(
        QuestionExtractionService,
        lambda: QuestionExtractionService(llm_client=container.get("llm_client")),
        singleton=False,
    )

    logger.info("DI container initialized")


def bind_models_to_database() -> None:
    """Bind all Peewee models to the database instance"""
    try:
        db_manager = get_database()
        db_instance = db_manager.get_db()

        # List of all models to bind
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

        # Bind each model to the database
        for model in models:
            model._meta.database = db_instance

        logger.info(f"Bound {len(models)} models to database")
    except Exception as e:
        logger.error(f"Error binding models to database: {e}")
        raise


def setup_database() -> None:
    """Initialize database by running migrations"""
    try:
        # First bind all models to the database
        bind_models_to_database()

        migration_manager = get_migration_manager()
        migration_manager.run_pending_migrations()
        logger.info("Database migrations completed")
    except Exception as e:
        logger.error(f"Error setting up database: {e}")
        raise


def setup_seeds(run_seeds: bool = False) -> None:
    """Setup database seeds"""
    if not run_seeds:
        logger.info("Seeds disabled (set RUN_SEEDS=true to enable)")
        return

    try:
        seed_manager = get_seed_manager()
        seed_manager.run_pending_seeds()
        logger.info("Database seeds completed")
    except Exception as e:
        logger.error(f"Error running seeds: {e}")
        # Don't raise - seeds are optional


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan context manager for startup and shutdown"""
    # Startup
    logger.info("Application startup")
    setup_di_container()
    setup_database()

    settings = get_settings()
    setup_seeds(run_seeds=getattr(settings, "run_seeds", False))

    # Start gRPC server
    grpc_manager = get_grpc_server_manager()
    grpc_manager.start()

    yield

    # Shutdown
    logger.info("Application shutdown")
    grpc_manager.stop()
    container = get_di_container()
    container.close_all()


def create_app() -> FastAPI:
    """Create and configure FastAPI application"""
    settings = get_settings()

    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        debug=settings.debug,
        lifespan=lifespan,
    )

    # Register exception handlers
    register_exception_handlers(app)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins_list,
        allow_credentials=settings.cors_allow_credentials,
        allow_methods=settings.cors_allow_methods_list,
        allow_headers=settings.cors_allow_headers_list,
    )

    # Include routers
    app.include_router(ai_router, prefix="/ai", tags=["ai"])
    app.include_router(document_router, prefix="/documents", tags=["documents"])
    app.include_router(page_router, prefix="/pages", tags=["pages"])
    app.include_router(question_router, prefix="/questions", tags=["questions"])

    @app.get("/")
    async def root():
        return create_response(
            data={
                "message": "Welcome to FastAPI Minimal Template",
                "app": settings.app_name,
                "version": settings.app_version,
            },
            message=f"Welcome to {settings.app_name}",
        )

    @app.get("/health")
    async def health_check():
        return create_response(
            data={
                "status": "ok",
                "app": settings.app_name,
            },
            message="Health check passed",
        )

    return app


# Create app instance
app = create_app()
