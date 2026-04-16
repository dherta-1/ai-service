from __future__ import annotations

import asyncio
import logging
import re
from pathlib import Path
from typing import TypedDict

from src.llm.base import GenerationConfig
from src.shared.base.base_pipeline import BasePipeline

logger = logging.getLogger(__name__)


class ContentValidationInput(TypedDict):
    image_path: Path
    page_number: int
    markdown_content: str


class ContentValidationOutput(TypedDict):
    page_number: int
    content: str


class ContentValidationPipeline(
    BasePipeline[ContentValidationInput, ContentValidationOutput]
):
    """Validate and normalize OCR markdown using multimodal LLM input."""

    def __init__(self, llm_client, prompt_template: str):
        self.llm_client = llm_client
        self.prompt_template = prompt_template

    def validate(self, payload: ContentValidationInput) -> None:
        image_path = payload.get("image_path")
        if not isinstance(image_path, Path) or not image_path.exists():
            raise FileNotFoundError(f"Image path not found: {image_path}")

    def postprocess(self, result: ContentValidationOutput) -> ContentValidationOutput:
        """Validate output structure before returning."""
        if not isinstance(result, dict):
            logger.error(
                f"ContentValidationPipeline postprocess: Invalid result type {type(result)}"
            )
            return {"page_number": 0, "content": ""}

        if "page_number" not in result or "content" not in result:
            logger.error(
                f"ContentValidationPipeline postprocess: Missing required keys. Got: {list(result.keys())}"
            )
            return {"page_number": result.get("page_number", 0), "content": ""}

        return result

    async def process(self, payload: ContentValidationInput) -> ContentValidationOutput:
        page_number = payload["page_number"]
        markdown_content = (payload.get("markdown_content") or "").strip()
        image_path = payload["image_path"]

        if not markdown_content:
            return {"page_number": page_number, "content": ""}

        if self.llm_client is None:
            return {"page_number": page_number, "content": markdown_content}

        prompt = self.prompt_template.format(markdown_content=markdown_content)

        try:
            raw_response = await asyncio.to_thread(
                self.llm_client.generate_file,
                str(image_path),
                prompt,
                GenerationConfig(temperature=0.1, response_mime_type="text/plain"),
            )
            normalized_content = self._extract_markdown(raw_response)
            if not normalized_content:
                normalized_content = markdown_content
            return {"page_number": page_number, "content": normalized_content}
        except Exception as exc:
            logger.warning(
                "LLM validation failed for page %s, fallback to OCR markdown: %s",
                page_number,
                exc,
            )
            return {"page_number": page_number, "content": markdown_content}

    @staticmethod
    def _extract_markdown(raw_text: str) -> str:
        text = (raw_text or "").strip()
        if not text:
            return ""

        fenced = re.findall(
            r"```(?:markdown|md)?\s*([\s\S]*?)\s*```", text, re.IGNORECASE
        )
        if fenced:
            return fenced[0].strip()

        return text
