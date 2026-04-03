"""OCR client registry and factory."""

from __future__ import annotations

import logging
from typing import Dict, Optional, Type

from src.ocr.base import BaseOCRClient, OCRConfig
from src.ocr.ppstructure.service import PPStructureOCRClient

logger = logging.getLogger(__name__)


class OCRRegistry:
    """Registry for managing OCR client creation and caching."""

    _providers: Dict[str, Type[BaseOCRClient]] = {
        "ppstructure": PPStructureOCRClient,
    }

    def __init__(self) -> None:
        self._clients: Dict[str, BaseOCRClient] = {}
        self._configs: Dict[str, OCRConfig] = {}

    @classmethod
    def register_provider(cls, name: str, client_class: Type[BaseOCRClient]) -> None:
        cls._providers[name] = client_class
        logger.info("Registered OCR provider: %s", name)

    @classmethod
    def get_available_providers(cls) -> list[str]:
        return list(cls._providers.keys())

    def create_client(
        self, config: OCRConfig, client_id: Optional[str] = None
    ) -> BaseOCRClient:
        provider = config.provider.lower()
        if provider not in self._providers:
            raise ValueError(
                f"Unknown OCR provider: {provider}. "
                f"Available providers: {self.get_available_providers()}"
            )

        if client_id and client_id in self._clients:
            logger.info("Using cached OCR client: %s", client_id)
            return self._clients[client_id]

        client = self._providers[provider](config)
        if client_id:
            self._clients[client_id] = client
            self._configs[client_id] = config
        return client

    def get_client(self, client_id: str) -> Optional[BaseOCRClient]:
        return self._clients.get(client_id)

    def remove_client(self, client_id: str) -> bool:
        client = self._clients.get(client_id)
        if client is None:
            return False

        try:
            client.close()
        finally:
            self._clients.pop(client_id, None)
            self._configs.pop(client_id, None)

        return True

    def close_all(self) -> None:
        for client_id in list(self._clients.keys()):
            self.remove_client(client_id)


_registry: OCRRegistry | None = None


def get_ocr_registry() -> OCRRegistry:
    global _registry
    if _registry is None:
        _registry = OCRRegistry()
    return _registry


def init_ocr_registry(registry: OCRRegistry | None = None) -> OCRRegistry:
    global _registry
    _registry = registry or OCRRegistry()
    return _registry


def register_ocr_registry(container, key: str = "ocr_registry") -> OCRRegistry:
    from src.container import DIContainer

    if not isinstance(container, DIContainer):
        raise TypeError("container must be an instance of DIContainer")

    registry = get_ocr_registry()
    container.register_singleton(key, registry)
    logger.info("Registered ocr_registry in DI container with key %s", key)
    return registry
