"""Question Extraction + Embed Worker core service.

Uses pipelines:
  1. QuestionExtractionPipeline — extract questions from page markdown
  2. AnswerParsingPipeline — parse answers from JSON strings to structured format
  3. QuestionEmbeddingPipeline — embed questions
  4. QuestionGroupingPipeline — find or create groups
  5. QuestionPersistencePipeline — persist to DB
"""

from __future__ import annotations

import logging
from typing import Any, Dict
from uuid import UUID

from src.pipelines.question_extraction import QuestionExtractionPipeline
from src.pipelines.answer_parsing import AnswerParsingPipeline
from src.pipelines.question_embedding import QuestionEmbeddingPipeline
from src.pipelines.question_grouping import QuestionGroupingPipeline
from src.pipelines.question_persistence import QuestionPersistencePipeline
from src.repos.page_repo import PageRepository
from src.repos.task_repo import TaskRepository
from src.shared.constants.general import Status

logger = logging.getLogger(__name__)


class QuestionExtractionService:
    """Question Extraction + Embed Worker.

    Receives a page_id, loads page content, runs extraction/embedding/grouping/persistence pipelines.
    """

    def __init__(
        self,
        llm_client,
    ):
        self._llm_client = llm_client
        self._extraction_pipeline = QuestionExtractionPipeline(
            llm_client=llm_client
        )
        self._answer_parsing_pipeline = AnswerParsingPipeline()
        self._embedding_pipeline = QuestionEmbeddingPipeline(llm_client=llm_client)
        self._grouping_pipeline = QuestionGroupingPipeline()
        self._persistence_pipeline = QuestionPersistencePipeline()
        self._page_repo = PageRepository()
        self._task_repo = TaskRepository()

    async def process_page(
        self,
        page_id: UUID,
        task_id: UUID,
        is_final_page: bool,
    ) -> Dict[str, Any]:
        """Extract, parse answers, embed, group, and persist questions for one page.

        Args:
            page_id: The Page record to process.
            task_id: The Task tracking this document extraction.
            is_final_page: True when this is the last page of the document.

        Returns:
            dict with persisted_count, failed_count, errors.
        """
        page = self._page_repo.get_by_id(page_id)
        if page is None:
            raise ValueError(f"Page {page_id} not found")

        markdown = (page.content or "").strip()
        if not markdown:
            logger.warning(
                "Page %s has no content, skipping question extraction", page_id
            )
            self._mark_page_skipped(task_id, is_final_page)
            return {"persisted_count": 0, "failed_count": 0, "errors": []}

        # Build overlap_content for question extraction
        overlap_content = None
        if page.overlap_content:
            overlap_content = {
                "previous_page": page.page_number - 1,
                "content": page.overlap_content,
            }

        # Pipeline 1: Extract
        extraction_result = await self._extraction_pipeline.process(
            {
                "page_number": page.page_number,
                "markdown_content": markdown,
                "overlap_content": overlap_content,
            }
        )
        questions = extraction_result.get("questions", [])
        logger.info(
            "Extracted %d questions from page %s",
            len(questions),
            page_id,
        )

        if not questions:
            self._mark_page_skipped(task_id, is_final_page)
            return {"persisted_count": 0, "failed_count": 0, "errors": []}

        # Pipeline 2: Parse answers
        parse_result = await self._answer_parsing_pipeline.process({"questions": questions})
        questions = parse_result.get("questions", [])

        # Pipeline 3: Embed
        embed_result = await self._embedding_pipeline.process({"questions": questions})
        questions = embed_result.get("questions", [])

        # Pipeline 4: Group
        group_result = await self._grouping_pipeline.process({"questions": questions})
        grouped_questions = group_result.get("grouped_questions", [])

        # Pipeline 5: Persist
        persist_result = await self._persistence_pipeline.process(
            {
                "page_id": str(page_id),
                "page_number": page.page_number,
                "task_id": str(task_id),
                "is_final_page": is_final_page,
                "questions": grouped_questions,
            }
        )

        return persist_result

    def _mark_page_skipped(self, task_id: UUID, is_final_page: bool) -> None:
        task = self._task_repo.get_by_id(task_id)
        if task is None:
            return
        task.processed_pages = (task.processed_pages or 0) + 1
        total = task.total_pages or 1
        task.progress = min(task.processed_pages / total, 1.0)
        if is_final_page:
            task.status = Status.COMPLETED.value
            task.progress = 1.0
        task.save()
