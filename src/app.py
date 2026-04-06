from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from src.settings import get_settings
from src.container import get_di_container, initialize_di_container
from src.lib.db.peewee import get_database
from src.lib.db.migration_manager import get_migration_manager
from src.lib.db.seed_manager import get_seed_manager
from src.lib.cachedb.redis import get_cache_client
from src.lib.s3_client import get_s3_client
from src.llm.registry import get_llm_registry, register_llm_registry
from src.llm.base import LLMConfig
from src.ocr.registry import register_ocr_registry
from src.ocr.base import OCRConfig
from src.lib.grpc_server import get_grpc_server_manager
from src.routes.ai_route import router as ai_router
from src.shared.response.exception_handler import register_exception_handlers
from src.shared.response.response_models import create_response
from src.repos.project_metadata_repo import ProjectMetadataRepo
from src.services.document_processing_service import DocumentProcessingService
import logging

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
    s3_bucket = settings.aws_s3_bucket if hasattr(settings, "aws_s3_bucket") else None
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

    # Register document processing service with DI dependencies
    container.register_type(
        DocumentProcessingService,
        lambda: DocumentProcessingService(
            ocr_client=container.get("ocr_client"),
            s3_client=container.get("s3_client"),
            s3_bucket=s3_bucket,
        ),
        singleton=False,
    )

    # Register services with their dependencies

    logger.info("DI container initialized")


def bind_models_to_database() -> None:
    """Bind all Peewee models to the database instance"""
    try:
        db_manager = get_database()
        db_instance = db_manager.get_db()

        # List of all models to bind
        models = [
            # Add your Peewee models here, e.g.: Document, Page, etc.
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
