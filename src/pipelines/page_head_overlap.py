from __future__ import annotations

import logging
from typing import Optional, TypedDict

from src.shared.base.base_pipeline import BasePipeline

logger = logging.getLogger(__name__)


class OverlapContent(TypedDict):
    previous_page: int
    content: str


class PageHeadOverlapInput(TypedDict):
    page_number: int
    markdown_content: str
    previous_page_content: Optional[str]


class PageHeadOverlapOutput(TypedDict):
    page_number: int
    markdown_content: str
    overlap_content: Optional[OverlapContent]


class PageHeadOverlapPipeline(
    BasePipeline[PageHeadOverlapInput, PageHeadOverlapOutput]
):
    """Overlap previous page content with current page to resolve questions spanning 2 pages.

    This pipeline handles the case where a question or content spans across page boundaries.
    It overlaps the last n characters of the previous page with the beginning of the current
    page to provide context for question extraction.

    The first page (page_number = 1) is not overlapped since there is no previous page.
    """

    def __init__(self, overlap_char_count: int = 500):
        """Initialize the pipeline.

        Args:
            overlap_char_count: Number of characters to overlap from the end of
                                the previous page. Default is 500 characters.
        """
        self.overlap_char_count = overlap_char_count

    def validate(self, payload: PageHeadOverlapInput) -> None:
        """Validate input payload."""
        if "page_number" not in payload or "markdown_content" not in payload:
            raise ValueError(
                "Missing required input fields: page_number, markdown_content"
            )

    def postprocess(self, result: PageHeadOverlapOutput) -> PageHeadOverlapOutput:
        """Validate output structure before returning."""
        if not isinstance(result, dict):
            logger.error(
                f"PageHeadOverlapPipeline postprocess: Invalid result type {type(result)}"
            )
            return {
                "page_number": 0,
                "markdown_content": "",
                "overlap_content": None,
            }

        if (
            "page_number" not in result
            or "markdown_content" not in result
            or "overlap_content" not in result
        ):
            logger.error(
                f"PageHeadOverlapPipeline postprocess: Missing required keys. Got: {list(result.keys())}"
            )
            return {
                "page_number": result.get("page_number", 0),
                "markdown_content": result.get("markdown_content", ""),
                "overlap_content": None,
            }

        return result

    async def process(self, payload: PageHeadOverlapInput) -> PageHeadOverlapOutput:
        """Process the payload and create overlap content if applicable.

        For the first page (page_number = 1), no overlap is created.
        For subsequent pages, the last overlap_char_count characters from the
        previous page are extracted to provide context for question extraction.
        """
        page_number = payload["page_number"]
        markdown_content = (payload.get("markdown_content") or "").strip()
        previous_page_content = payload.get("previous_page_content")

        # For the first page, no overlap is needed
        if page_number == 1 or not previous_page_content:
            logger.debug(
                f"Page {page_number}: No overlap needed (first page or no previous content)"
            )
            return {
                "page_number": page_number,
                "markdown_content": markdown_content,
                "overlap_content": None,
            }

        # Extract the overlap content from the previous page
        previous_content = (previous_page_content or "").strip()
        if not previous_content:
            logger.debug(
                f"Page {page_number}: No overlap content (previous page is empty)"
            )
            return {
                "page_number": page_number,
                "markdown_content": markdown_content,
                "overlap_content": None,
            }

        # Get the last n characters from the previous page
        overlap_text = previous_content[-self.overlap_char_count :]

        logger.info(
            f"Page {page_number}: Created overlap content from page {page_number - 1} "
            f"({len(overlap_text)} chars)"
        )

        overlap_content: OverlapContent = {
            "previous_page": page_number - 1,
            "content": overlap_text,
        }

        return {
            "page_number": page_number,
            "markdown_content": markdown_content,
            "overlap_content": overlap_content,
        }
