from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Generic, TypeVar

TIn = TypeVar("TIn")
TOut = TypeVar("TOut")


class BasePipeline(ABC, Generic[TIn, TOut]):
    """Reusable async pipeline with input validation and post-processing hooks."""

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
        raise NotImplementedError

    def postprocess(self, result: TOut) -> TOut:
        """Optional post-processing hook."""
        return result
