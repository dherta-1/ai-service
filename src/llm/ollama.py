"""Ollama LLM Client Implementation"""

import logging
import base64
import mimetypes
import time
from pathlib import Path
from typing import Optional, List, Dict, Any
from .base import BaseLLMClient, LLMConfig, GenerationConfig
from src.shared.utils.retry import retry_sync, RetryConfig

logger = logging.getLogger(__name__)


class OllamaClient(BaseLLMClient):
    """Ollama LLM Client using ollama library"""

    def __init__(self, config: LLMConfig):
        """
        Initialize Ollama client

        Args:
            config: LLMConfig with Ollama-specific settings
        """
        super().__init__(config)
        self.host = config.host or "http://localhost:11434"
        self.client = self._create_client()

    def _create_client(self):
        """Create and configure Ollama client"""
        try:
            from ollama import Client, AsyncClient
        except ImportError:
            raise ImportError(
                "ollama is not installed. " "Install it with: pip install ollama"
            )

        logger.info(f"Creating Ollama client (host={self.host})")

        # Store the client classes for later use
        self._client_class = Client
        self._async_client_class = AsyncClient

        # Create sync client
        client = Client(host=self.host)

        return client

    @retry_sync(RetryConfig(max_retries=3))
    def _generate_with_retry(self, prompt: str, options: Dict[str, Any], **kwargs) -> str:
        """Internal method with retry logic for generate"""
        response = self.client.generate(
            model=self.model,
            prompt=prompt,
            stream=False,
            options=options,
            **kwargs,
        )
        if response and "response" in response:
            return response["response"]
        logger.warning("Empty response from Ollama")
        return ""

    def generate(
        self, prompt: str, gen_config: Optional[GenerationConfig] = None, **kwargs
    ) -> str:
        """
        Generate text response from a single prompt

        Args:
            prompt: Input text prompt
            gen_config: GenerationConfig with temperature, max_tokens, etc.
            **kwargs: Additional parameters passed to generate

        Returns:
            Generated text response
        """
        config = gen_config or GenerationConfig()

        try:
            options = {
                "temperature": config.temperature,
                **({"num_predict": config.max_tokens} if config.max_tokens else {}),
            }
            return self._generate_with_retry(prompt, options, **kwargs)
        except Exception as e:
            logger.error(f"Error generating content from Ollama: {e}")
            raise

    @retry_sync(RetryConfig(max_retries=3))
    def _chat_with_retry(self, messages: List[Dict[str, str]], options: Dict[str, Any], **kwargs) -> str:
        """Internal method with retry logic for chat"""
        response = self.client.chat(
            model=self.model,
            messages=messages,
            stream=False,
            options=options,
            **kwargs,
        )
        if response and "message" in response:
            return response["message"]["content"]
        logger.warning("Empty response from Ollama chat")
        return ""

    def chat(
        self,
        messages: List[Dict[str, str]],
        gen_config: Optional[GenerationConfig] = None,
        **kwargs,
    ) -> str:
        """
        Generate response from chat message history

        Args:
            messages: List of message dicts with 'role' and 'content'
            gen_config: GenerationConfig with temperature, max_tokens, etc.
            **kwargs: Additional parameters passed to chat

        Returns:
            Generated text response
        """
        config = gen_config or GenerationConfig()

        try:
            options = {
                "temperature": config.temperature,
                **({"num_predict": config.max_tokens} if config.max_tokens else {}),
            }
            return self._chat_with_retry(messages, options, **kwargs)
        except Exception as e:
            logger.error(f"Error in Ollama chat: {e}")
            raise

    def stream_generate(
        self, prompt: str, gen_config: Optional[GenerationConfig] = None, **kwargs
    ):
        """
        Stream generated text response

        Args:
            prompt: Input text prompt
            gen_config: GenerationConfig with temperature, max_tokens, etc.
            **kwargs: Additional parameters passed to generate

        Yields:
            Text chunks of the response
        """
        config = gen_config or GenerationConfig()

        try:
            response_stream = self.client.generate(
                model=self.model,
                prompt=prompt,
                stream=True,
                options={
                    "temperature": config.temperature,
                    **({"num_predict": config.max_tokens} if config.max_tokens else {}),
                },
                **kwargs,
            )

            for chunk in response_stream:
                if chunk and "response" in chunk:
                    yield chunk["response"]

        except Exception as e:
            logger.error(f"Error streaming content from Ollama: {e}")
            raise

    def stream_chat(
        self,
        messages: List[Dict[str, str]],
        gen_config: Optional[GenerationConfig] = None,
        **kwargs,
    ):
        """
        Stream response from chat message history

        Args:
            messages: List of message dicts with 'role' and 'content'
            gen_config: GenerationConfig with temperature, max_tokens, etc.
            **kwargs: Additional parameters passed to chat

        Yields:
            Text chunks of the response
        """
        config = gen_config or GenerationConfig()

        try:
            response_stream = self.client.chat(
                model=self.model,
                messages=messages,
                stream=True,
                options={
                    "temperature": config.temperature,
                    **({"num_predict": config.max_tokens} if config.max_tokens else {}),
                },
                **kwargs,
            )

            for chunk in response_stream:
                if chunk and "message" in chunk:
                    content = chunk["message"].get("content", "")
                    if content:
                        yield content

        except Exception as e:
            logger.error(f"Error streaming chat from Ollama: {e}")
            raise

    def generate_file(
        self,
        file_path: str,
        prompt: Optional[str] = None,
        gen_config: Optional[GenerationConfig] = None,
        **kwargs,
    ) -> str:
        """Generate from local file for Ollama (with base64 fallback)."""
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")

        config = gen_config or GenerationConfig()
        mime_type, _ = mimetypes.guess_type(file_path)

        with path.open("rb") as f:
            raw_bytes = f.read()

        if mime_type and mime_type.startswith("text"):
            file_text = raw_bytes.decode("utf-8", errors="replace")
            chat_message = [
                {
                    "role": "user",
                    "content": prompt
                    or f"Please analyze the contents of {path.name}."
                    + "\n\nFile content:\n"
                    + file_text,
                },
            ]
        else:
            b64 = base64.b64encode(raw_bytes).decode("utf-8")
            chat_message = [
                {
                    "role": "user",
                    "content": prompt
                    or f"The file {path.name} is binary. Please analyze the contents based on the provided base64 encoding.",
                    "file": [b64],
                },
            ]

        return self.chat(chat_message, gen_config=config, **kwargs)

    def stream_generate_file(
        self,
        file_path: str,
        prompt: Optional[str] = None,
        gen_config: Optional[GenerationConfig] = None,
        **kwargs,
    ):
        """Stream generate from local file for Ollama."""
        # Streaming for binary fallback is essentially text-generation on encoded prompt
        response = self.generate_file(
            file_path, prompt=prompt, gen_config=gen_config, **kwargs
        )
        yield response

    def close(self) -> None:
        """Close client and cleanup resources"""
        # Ollama client doesn't typically require explicit cleanup
        # but we log for consistency
        logger.info("Ollama client closed")

    @retry_sync(RetryConfig(max_retries=3))
    def _embed_with_retry(self, input: list[str], **kwargs) -> list[list[float]]:
        """Internal method with retry logic for embed"""
        response = self.client.embed(
            model=self.embedding_model,
            input=input,
            dimensions=self.embedding_dimension,
            **kwargs,
        )
        if response and "embeddings" in response:
            return response["embeddings"]
        logger.warning("Empty embedding response from Ollama")
        raise ValueError("Failed to generate embeddings from Ollama")

    def embed(self, input: str | list[str], **kwargs) -> list[list[float]]:
        """
        Generate embeddings for input text(s) using Ollama

        Args:
            input: Single string or list of strings to embed
            **kwargs: Additional provider-specific parameters

        Returns:
            List of embedding vectors corresponding to input strings

        Raises:
            ValueError: If input is empty
            Exception: If embedding generation fails
        """
        if isinstance(input, str):
            input = [input]
        elif not input:
            raise ValueError("Input cannot be empty")

        try:
            embeddings = self._embed_with_retry(input, **kwargs)
            logger.info(f"Generated {len(embeddings)} embedding(s) using Ollama")
            return embeddings
        except Exception as e:
            logger.error(f"Error generating embeddings from Ollama: {e}")
            raise

    @retry_sync(RetryConfig(max_retries=2))
    def _health_check_with_retry(self):
        """Internal method with retry logic for health check"""
        return self.client.list()

    def health_check(self) -> bool:
        """
        Check if Ollama server is accessible

        Returns:
            True if server is accessible, False otherwise
        """
        try:
            self._health_check_with_retry()
            return True
        except Exception as e:
            logger.error(f"Ollama health check failed: {e}")
            return False

    @retry_sync(RetryConfig(max_retries=2))
    def _list_models_with_retry(self):
        """Internal method with retry logic for listing models"""
        return self.client.list()

    def list_models(self) -> List[str]:
        """
        Get list of available models on Ollama server

        Returns:
            List of model names
        """
        try:
            response = self._list_models_with_retry()
            if response and "models" in response:
                return [model["name"] for model in response["models"]]
            return []
        except Exception as e:
            logger.error(f"Error listing Ollama models: {e}")
            return []
