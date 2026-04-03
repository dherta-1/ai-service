"""PPStructure OCR client implementation."""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

from src.ocr.base import BaseOCRClient, OCRConfig
from src.ocr.dtos import OCRExtractionResult, OCRImageRequest
from src.ocr.ppstructure.mapper import map_ppstructure_results

logger = logging.getLogger(__name__)


class PPStructureOCRClient(BaseOCRClient):
    """OCR client using PaddleOCR PPStructureV3."""

    _ENGINE_CACHE: dict[tuple[str, bool], Any] = {}

    def __init__(self, config: OCRConfig):
        super().__init__(config)
        self._engine = self._get_or_create_engine()

    def _get_or_create_engine(self):
        key = (self.config.lang, self.config.use_gpu)
        cached = self._ENGINE_CACHE.get(key)
        if cached is not None:
            logger.info("Using cached PPStructure engine (lang=%s, gpu=%s)", *key)
            return cached

        engine = self._create_engine()
        self._ENGINE_CACHE[key] = engine
        return engine

    def _create_engine(self):
        # Avoid network source checks every startup; model files are cached locally.
        os.environ.setdefault("PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK", "True")

        try:
            from paddleocr import PPStructureV3
        except ImportError as exc:
            raise ImportError(
                "paddleocr is not installed. Install it with: pip install paddleocr[all]"
            ) from exc

        device = "gpu" if self.config.use_gpu else "cpu"
        logger.info(
            "Creating PPStructureV3 client (lang=%s, device=%s)",
            self.config.lang,
            device,
        )

        return PPStructureV3(
            use_doc_orientation_classify=False,
            use_doc_unwarping=False,
            use_textline_orientation=False,
            device=device,
            lang=self.config.lang,
            enable_mkldnn=False,
        )

    def extract(self, request: OCRImageRequest) -> OCRExtractionResult:
        image_path = request.resolved_path()
        if not image_path.exists() or not image_path.is_file():
            raise FileNotFoundError(f"Input image not found: {image_path}")

        raw_results = self._engine.predict(str(image_path))
        raw_pages = [self._to_dict(page_result) for page_result in raw_results]
        return map_ppstructure_results(image_path=str(image_path), raw_pages=raw_pages)

    def close(self) -> None:
        """Release resources held by PPStructure engine."""
        # PPStructureV3 does not require explicit cleanup in current SDK.
        return None

    @staticmethod
    def _to_dict(raw_page: Any) -> dict[str, Any]:
        # PPStructure may wrap actual page data in `res`.
        wrapped = getattr(raw_page, "res", None)
        if wrapped is not None:
            return PPStructureOCRClient._to_dict(wrapped)

        if isinstance(raw_page, dict):
            if "res" in raw_page and raw_page["res"] is not None:
                return PPStructureOCRClient._to_dict(raw_page["res"])
            return raw_page

        for attr in ("to_dict", "model_dump", "dict"):
            method = getattr(raw_page, attr, None)
            if callable(method):
                value = method()
                if isinstance(value, dict):
                    return value

        if hasattr(raw_page, "json"):
            json_value = getattr(raw_page, "json")
            if isinstance(json_value, dict):
                return json_value

        if hasattr(raw_page, "__dict__"):
            value = getattr(raw_page, "__dict__")
            if isinstance(value, dict):
                return value

        raise TypeError(f"Unsupported PPStructure page result type: {type(raw_page)!r}")
