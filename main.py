import asyncio
import logging
import argparse
import platform
import sys
from typing import Literal

# Must be set before any event loop is created (required for Playwright on Windows)
if platform.system() == "Windows":
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


def run_api_app() -> None:
    """Run the FastAPI application."""
    logger.info("Starting API app...")
    import uvicorn
    from src.app import app
    from src.settings import get_settings

    settings = get_settings()
    uvicorn.run(
        "src.app:app",
        host=settings.host,
        port=settings.port,
        reload=settings.debug,
        reload_excludes=["output", "output/**", "uploads", "uploads/**", "*.log"],
        log_level="info",
    )


def run_document_extraction_worker() -> None:
    """Run the document extraction event worker."""
    logger.info("Starting document extraction worker...")
    from src.workers.document_extraction_worker import main as worker_main

    worker_main()


def run_questions_extraction_worker() -> None:
    """Run the questions extraction event worker."""
    logger.info("Starting questions extraction worker...")
    from src.workers.questions_extraction_worker import main as worker_main

    worker_main()

def run_audit_log_worker() -> None:
    """Run the questions extraction event worker."""
    logger.info("Starting questions extraction worker...")
    from src.workers.audit_log_worker import main as worker_main

    worker_main()


def main():
    parser = argparse.ArgumentParser(
        description="AI Service - Run different runtime modes",
        prog="python main.py",
    )
    parser.add_argument(
        "mode",
        type=str,
        choices=["api", "document-worker", "questions-worker", "audit-log-worker"],
        help="Runtime mode to start",
    )

    # Handle no arguments case
    if len(sys.argv) == 1:
        parser.print_help()
        sys.exit(1)

    args = parser.parse_args()
    mode: Literal["api", "document-worker", "questions-worker", "audit-log-worker"] = args.mode

    try:
        if mode == "api":
            run_api_app()
        elif mode == "document-worker":
            run_document_extraction_worker()
        elif mode == "questions-worker":
            run_questions_extraction_worker()
        elif mode == "audit-log-worker":
            run_audit_log_worker()
    except KeyboardInterrupt:
        logger.info("Interrupted by user")
        sys.exit(0)
    except Exception as e:
        logger.error("Fatal error: %s", e, exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
