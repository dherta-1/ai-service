import asyncio
import platform

# Set before any event loop is created. Needed for Playwright subprocess on Windows.
# With uvicorn --reload, the worker process imports this module directly (not via main.py),
# so the policy must also be set here.
if platform.system() == "Windows":
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

from fastapi import FastAPI, APIRouter
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from src.services.exam_service import ExamService
from src.services.exam_attempt_service import ExamAttemptService
from src.services.token_service import ExamTokenService
from src.services.answer_scoring_service import AnswerScoringService
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
from src.lib.playwright import PlaywrightManager
from src.routes.ai_route import router as ai_router
from src.routes.auth_route import router as auth_router
from src.routes.document_route import router as document_router
from src.routes.exam_route import router as exam_router
from src.routes.file_route import router as file_router
from src.routes.page_route import router as page_router
from src.routes.question_route import router as question_router
from src.routes.task_route import router as task_router
from src.routes.user_route import router as user_router
from src.routes.subject_route import router as subject_router
from src.routes.topic_route import router as topic_router
from src.routes.audit_log_route import router as audit_log_router
from src.shared.response.exception_handler import register_exception_handlers
from src.shared.response.response_models import create_response

# from src.services.document_processing_service import DocumentProcessingService
from src.services.auth_service import AuthService
from src.services.document_service import DocumentService
from src.services.file_service import FileService
from src.services.task_service import TaskService
from src.services.question_service import QuestionService
from src.services.page_service import PageService
from src.services.user_service import UserService
from src.services.subject_service import SubjectService
from src.services.topic_service import TopicService
from src.services.audit_log_service import AuditLogService
from src.services.core.document_extraction_service import DocumentExtractionService
from src.services.core.question_extraction_service import QuestionExtractionService
from src.services.core.base_exam_generation_service import BaseExamGenerationService
from src.services.core.exam_instance_export_service import ExamInstanceExportService
from src.services.core.variant_exam_generation_service import (
    VariantExamGenerationService,
)
from src.services.core.question_mutation_service import QuestionMutationService
from src.services.core.exam_mutation_service import ExamMutationService
from src.services.core.generate_answer_service import GenerateAnswerService
import logging
from src.entities.answer import Answer
from src.entities.attempt_token_mapping import AttemptTokenMapping
from src.entities.document import Document
from src.entities.exam_instance import ExamInstance
from src.entities.exam_template import ExamTemplate
from src.entities.exam_test_section import ExamTestSection
from src.entities.file_metadata import FileMetadata
from src.entities.page import Page
from src.entities.question import Question
from src.entities.question_exam_test import QuestionExamTest
from src.entities.question_group import QuestionGroup
from src.entities.subject import Subject
from src.entities.task import Task
from src.entities.topic import Topic
from src.entities.user import User
from src.entities.user_test_attempt import UserTestAttempt
from src.entities.user_test_attempt_answer import UserTestAttemptAnswer
from src.entities.audit_log import AuditLog

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

    # Register auth / user services
    user_service = UserService()
    container.register_singleton("user_service", user_service)
    container.register_singleton(
        "auth_service",
        AuthService(
            user_service=user_service, cache=container.get("cache"), settings=settings
        ),
    )

    # Register core services as singletons
    container.register_singleton("document_service", DocumentService())
    container.register_singleton("file_service", FileService())
    container.register_singleton("task_service", TaskService())
    container.register_singleton("question_service", QuestionService())
    container.register_singleton("page_service", PageService())
    container.register_singleton("exam_service", ExamService())
    container.register_singleton("exam_token_service", ExamTokenService())
    container.register_singleton("answer_scoring_service", AnswerScoringService())
    container.register_singleton("exam_attempt_service", ExamAttemptService())
    container.register_singleton("subject_service", SubjectService(SubjectRepository()))
    container.register_singleton("topic_service", TopicService(TopicRepository()))
    container.register_singleton("audit_log_service", AuditLogService())

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

    # Register Playwright manager as singleton (before exam export service)
    playwright_manager = PlaywrightManager()
    container.register_singleton("playwright_manager", playwright_manager)

    # Register exam export service
    container.register_type(
        ExamInstanceExportService,
        lambda: ExamInstanceExportService(
            s3_client=container.get("s3_client"),
            s3_bucket=s3_bucket or "",
            exam_service=container.get("exam_service"),
            file_service=container.get("file_service"),
            playwright_manager=container.get("playwright_manager"),
        ),
    )

    # Register exam generation services as singletons
    container.register_type(
        BaseExamGenerationService,
        lambda: BaseExamGenerationService(llm_client=container.get("llm_client")),
    )
    container.register_type(
        VariantExamGenerationService,
        lambda: VariantExamGenerationService(llm_client=container.get("llm_client")),
    )

    # Register question mutation service
    container.register_type(
        QuestionMutationService,
        lambda: QuestionMutationService(llm_client=container.get("llm_client")),
    )

    # Register exam mutation service
    container.register_type(
        ExamMutationService,
        lambda: ExamMutationService(),
    )

    # Register generate answer service
    container.register_type(
        GenerateAnswerService,
        lambda: GenerateAnswerService(
            llm_client=container.get("llm_client"),
            s3_client=container.get("s3_client"),
        ),
    )

    logger.info("DI container initialized")


def bind_models_to_database() -> None:
    """Bind all Peewee models to the database instance"""
    try:
        db_manager = get_database()
        db_instance = db_manager.get_db()

        # List of all models to bind
        models = [
            User,
            Answer,
            AttemptTokenMapping,
            Document,
            ExamInstance,
            ExamTemplate,
            ExamTestSection,
            FileMetadata,
            Page,
            Question,
            QuestionExamTest,
            QuestionGroup,
            Subject,
            Task,
            Topic,
            UserTestAttempt,
            UserTestAttemptAnswer,
            AuditLog,
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

    # Initialize Playwright
    container = get_di_container()
    playwright_manager = container.get("playwright_manager")
    await playwright_manager.initialize()

    # Start gRPC server
    grpc_manager = get_grpc_server_manager()
    grpc_manager.start()

    yield

    # Shutdown
    logger.info("Application shutdown")
    grpc_manager.stop()
    await playwright_manager.shutdown()
    container.close_all()


def create_app() -> FastAPI:
    """Create and configure FastAPI application"""
    settings = get_settings()

    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        debug=settings.debug,
        lifespan=lifespan,
        root_path="/api",
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
    app.include_router(auth_router, prefix="/auth", tags=["auth"])
    app.include_router(user_router, prefix="/users", tags=["users"])
    app.include_router(ai_router, prefix="/ai", tags=["ai"])
    app.include_router(document_router, prefix="/documents", tags=["documents"])
    app.include_router(file_router, prefix="/files", tags=["files"])
    app.include_router(task_router, prefix="/documents", tags=["tasks"])
    app.include_router(exam_router, prefix="/exams", tags=["exam"])
    app.include_router(page_router, prefix="/pages", tags=["pages"])
    app.include_router(question_router, prefix="/questions", tags=["questions"])
    app.include_router(subject_router, prefix="/subjects", tags=["subjects"])
    app.include_router(topic_router, prefix="/topics", tags=["topics"])
    app.include_router(audit_log_router, prefix="/audit-logs", tags=["audit-logs"])

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
