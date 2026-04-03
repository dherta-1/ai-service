"""Base OCR client interface and config."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

from .dtos import OCRExtractionResult, OCRImageRequest


@dataclass
class OCRConfig:
    """Configuration for OCR client initialization."""

    provider: str = "ppstructure"
    lang: str = "en"
    use_gpu: bool = False


class BaseOCRClient(ABC):
    """Abstract OCR client for image inputs."""

    def __init__(self, config: OCRConfig):
        self.config = config

    @abstractmethod
    def extract(self, request: OCRImageRequest) -> OCRExtractionResult:
        """Extract OCR blocks from a single image input."""
        raise NotImplementedError

    @abstractmethod
    def close(self) -> None:
        """Release provider resources if any."""
        raise NotImplementedError
