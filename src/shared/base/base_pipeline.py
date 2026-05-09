from __future__ import annotations

from abc import ABC, abstractmethod
import logging
from typing import Generic, TypeVar

TIn = TypeVar("TIn")
TOut = TypeVar("TOut")


class BasePipeline(ABC, Generic[TIn, TOut]):
    """Reusable async pipeline with input validation and post-processing hooks."""

    def __init__(self):
        self._logger = logging.getLogger(__name__)

    async def run(self, payload: TIn) -> TOut:
        """Execute pipeline end-to-end."""
        self.validate(payload)
        result = await self.process(payload)
        return self.postprocess(result)

    def validate(self, payload: TIn) -> None:
        """Validate pipeline input before processing."""
        return None

    @abstractmethod
    async def process(self, payload: TIn) -> TOut:
        """Core pipeline logic."""
        self._logger.info(f"Processing payload: {payload}")
        raise NotImplementedError

    def postprocess(self, result: TOut) -> TOut:
        """Optional post-processing hook."""
        return result
