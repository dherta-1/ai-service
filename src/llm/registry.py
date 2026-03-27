"""LLM Client Registry - Factory pattern for managing LLM clients"""

import logging
from typing import Type, Dict, Optional, Literal
from .base import BaseLLMClient, LLMConfig
from .gemini import GeminiClient
from .ollama import OllamaClient

logger = logging.getLogger(__name__)

# Type alias for provider types
ProviderType = Literal["gemini", "ollama"]


class LLMRegistry:
    """Registry for managing LLM client creation and configuration"""

    # Map of provider names to client classes
    _providers: Dict[str, Type[BaseLLMClient]] = {
        "gemini": GeminiClient,
        "ollama": OllamaClient,
    }

    def __init__(self):
        """Initialize registry"""
        self._clients: Dict[str, BaseLLMClient] = {}
        self._configs: Dict[str, LLMConfig] = {}

    @classmethod
    def register_provider(cls, name: str, client_class: Type[BaseLLMClient]) -> None:
        """
        Register a new LLM provider

        Args:
            name: Provider name identifier
            client_class: LLM client class
        """
        cls._providers[name] = client_class
        logger.info(f"Registered LLM provider: {name}")

    @classmethod
    def get_available_providers(cls) -> list[str]:
        """Get list of available providers"""
        return list(cls._providers.keys())

    def create_client(
        self, config: LLMConfig, client_id: Optional[str] = None
    ) -> BaseLLMClient:
        """
        Create an LLM client from configuration

        Args:
            config: LLM configuration
            client_id: Optional identifier for caching client

        Returns:
            Configured LLM client instance

        Raises:
            ValueError: If provider is not supported
        """
        provider = config.provider.lower()

        if provider not in self._providers:
            raise ValueError(
                f"Unknown LLM provider: {provider}. "
                f"Available providers: {self.get_available_providers()}"
            )

        # Check if client is already cached
        if client_id and client_id in self._clients:
            logger.info(f"Using cached client: {client_id}")
            return self._clients[client_id]

        # Create new client
        client_class = self._providers[provider]
        logger.info(f"Creating {provider} client (id={client_id})")

        try:
            client = client_class(config)

            # Cache if client_id provided
            if client_id:
                self._clients[client_id] = client
                self._configs[client_id] = config
                logger.info(f"Cached client: {client_id}")

            return client

        except Exception as e:
            logger.error(f"Error creating {provider} client: {e}")
            raise

    def get_client(self, client_id: str) -> Optional[BaseLLMClient]:
        """
        Get cached client by ID

        Args:
            client_id: Client identifier

        Returns:
            Client instance or None if not found
        """
        return self._clients.get(client_id)

    def get_config(self, client_id: str) -> Optional[LLMConfig]:
        """
        Get config for cached client by ID

        Args:
            client_id: Client identifier

        Returns:
            Config instance or None if not found
        """
        return self._configs.get(client_id)

    def list_clients(self) -> Dict[str, BaseLLMClient]:
        """Get all cached clients"""
        return self._clients.copy()

    def remove_client(self, client_id: str) -> bool:
        """
        Remove and close client

        Args:
            client_id: Client identifier

        Returns:
            True if client was removed, False if not found
        """
        if client_id in self._clients:
            try:
                self._clients[client_id].close()
                del self._clients[client_id]
                if client_id in self._configs:
                    del self._configs[client_id]
                logger.info(f"Removed client: {client_id}")
                return True
            except Exception as e:
                logger.error(f"Error removing client {client_id}: {e}")
                return False
        return False

    def close_all(self) -> None:
        """Close all cached clients"""
        for client_id in list(self._clients.keys()):
            self.remove_client(client_id)
        logger.info("All clients closed")

    def __enter__(self):
        """Context manager entry"""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit"""
        self.close_all()


# Global registry instance
_registry: Optional[LLMRegistry] = None


def get_llm_registry() -> LLMRegistry:
    """Get or create global LLM registry"""
    global _registry
    if _registry is None:
        _registry = LLMRegistry()
    return _registry


def init_llm_registry(registry: Optional[LLMRegistry] = None) -> LLMRegistry:
    """Initialize global LLM registry"""
    global _registry
    _registry = registry or LLMRegistry()
    return _registry


def register_llm_registry(container, key: str = "llm_registry") -> LLMRegistry:
    """Create/get global LLM registry and register it in DI container."""
    from src.container import DIContainer

    if not isinstance(container, DIContainer):
        raise TypeError("container must be an instance of DIContainer")

    registry = get_llm_registry()
    container.register_singleton(key, registry)
    logger.info("Registered llm_registry in DI container with key %s", key)
    return registry
