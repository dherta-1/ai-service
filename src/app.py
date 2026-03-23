from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from src.settings import get_settings
from src.container import get_di_container, initialize_di_container
from src.lib.db.peewee import get_database
from src.lib.db.migration_manager import get_migration_manager
from src.lib.db.seed_manager import get_seed_manager
from src.lib.cachedb.redis import get_cache_client
from src.lib.grpc_server import get_grpc_server_manager
from src.routes.system_route import router as system_router
from src.entities.project_metadata import ProjectMetadata
from src.shared.response.exception_handler import register_exception_handlers
from src.shared.response.response_models import create_response
from src.handlers.event_dispatcher import initialize_event_handlers
from src.repos.project_metadata_repo import ProjectMetadataRepo
from src.services.project_metadata_service import ProjectMetadataService
from src.lib.event_bus.kafka.producer import KafkaProducerImpl
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

    # Register repositories
    container.register_type(
        ProjectMetadataRepo, lambda: ProjectMetadataRepo(), singleton=False
    )

    # Register services with their dependencies
    container.register_type(
        ProjectMetadataService,
        lambda: ProjectMetadataService(repo=container.resolve(ProjectMetadataRepo)),
        singleton=False,
    )

    # Register a shared Kafka producer (default topic: project-events)
    container.register_type(
        KafkaProducerImpl,
        lambda: KafkaProducerImpl(topic="project-events"),
        singleton=True,
    )

    logger.info("DI container initialized")


def bind_models_to_database() -> None:
    """Bind all Peewee models to the database instance"""
    try:
        db_manager = get_database()
        db_instance = db_manager.get_db()

        # List of all models to bind
        models = [
            ProjectMetadata,
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

    # Initialize event handlers
    initialize_event_handlers()

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
    app.include_router(system_router, prefix="/system", tags=["system"])

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
