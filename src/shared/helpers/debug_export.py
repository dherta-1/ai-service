import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def export_pipeline_debug(
    pipeline_name: str,
    stage: str,
    data: Any,
    page_number: int | None = None,
) -> None:
    """Export pipeline debug data to /debug directory when debug mode is enabled.

    Args:
        pipeline_name: Name of the pipeline (e.g., 'content_extraction')
        stage: Stage name (e.g., 'input', 'output', 'error')
        data: Data to export (will be JSON-serialized)
        page_number: Optional page number for organization
    """
    from src.settings import get_settings

    settings = get_settings()
    if not settings.log_results:
        return

    try:
        debug_dir = Path("debug")
        debug_dir.mkdir(exist_ok=True)

        # Create pipeline-specific subdirectory
        pipeline_dir = debug_dir / pipeline_name
        pipeline_dir.mkdir(exist_ok=True)

        # Build filename
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:-3]
        page_suffix = f"_p{page_number}" if page_number is not None else ""
        filename = f"{stage}{page_suffix}_{timestamp}.json"
        filepath = pipeline_dir / filename

        # Write data
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, default=str, ensure_ascii=False)

        logger.debug(f"Exported {pipeline_name} {stage} to {filepath}")
    except Exception as e:
        logger.warning(f"Failed to export {pipeline_name} debug data: {e}")
