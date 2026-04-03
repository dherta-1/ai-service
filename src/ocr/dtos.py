"""DTOs for OCR image extraction."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

OCRContentType = Literal["text", "seal", "formula", "image"]


@dataclass
class BBoxRect:
    """Axis-aligned bounding box in pixel coordinates."""

    x1: float
    y1: float
    x2: float
    y2: float

    @classmethod
    def from_sequence(cls, coords: list[float] | tuple[float, ...]) -> "BBoxRect":
        if len(coords) != 4:
            raise ValueError("bbox must contain exactly 4 values: [x1, y1, x2, y2]")
        return cls(
            x1=float(coords[0]),
            y1=float(coords[1]),
            x2=float(coords[2]),
            y2=float(coords[3]),
        )


@dataclass
class OCRImageRequest:
    """Input request for OCR extraction from an image file."""

    image_path: str | Path

    def resolved_path(self) -> Path:
        return Path(self.image_path).expanduser().resolve()


@dataclass
class OCRItem:
    """A single OCR element extracted from an image."""

    bbox: BBoxRect
    content: str
    content_type: OCRContentType
    accuracy: float
    source_label: str | None = None


@dataclass
class OCRPageResult:
    """OCR output for one image page."""

    page_index: int
    width: int | None
    height: int | None
    items: list[OCRItem] = field(default_factory=list)
    raw: dict[str, Any] | None = None


@dataclass
class OCRExtractionResult:
    """OCR output container for an image input."""

    image_path: str
    pages: list[OCRPageResult] = field(default_factory=list)
