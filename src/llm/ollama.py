"""Ollama LLM Client Implementation"""

import logging
import base64
import mimetypes
import time
from pathlib import Path
from typing import Optional, List, Dict, Any
from .base import BaseLLMClient, LLMConfig, GenerationConfig

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
            response = self.client.generate(
                model=self.model,
                prompt=prompt,
                stream=False,
                options={
                    "temperature": config.temperature,
                    **({"num_predict": config.max_tokens} if config.max_tokens else {}),
                },
                **kwargs,
            )

            if response and "response" in response:
                return response["response"]
            else:
                logger.warning("Empty response from Ollama")
                return ""

        except Exception as e:
            logger.error(f"Error generating content from Ollama: {e}")
            raise

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
            response = self.client.chat(
                model=self.model,
                messages=messages,
                stream=False,
                options={
                    "temperature": config.temperature,
                    **({"num_predict": config.max_tokens} if config.max_tokens else {}),
                },
                **kwargs,
            )

            if response and "message" in response:
                return response["message"]["content"]
            else:
                logger.warning("Empty response from Ollama chat")
                return ""

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

    def health_check(self) -> bool:
        """
        Check if Ollama server is accessible

        Returns:
            True if server is accessible, False otherwise
        """
        try:
            # Try to list models as a health check
            self.client.list()
            return True
        except Exception as e:
            logger.error(f"Ollama health check failed: {e}")
            return False

    def list_models(self) -> List[str]:
        """
        Get list of available models on Ollama server

        Returns:
            List of model names
        """
        try:
            response = self.client.list()
            if response and "models" in response:
                return [model["name"] for model in response["models"]]
            return []
        except Exception as e:
            logger.error(f"Error listing Ollama models: {e}")
            return []
