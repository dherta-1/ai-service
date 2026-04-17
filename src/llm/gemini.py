"""Google Gemini LLM Client Implementation"""

import logging
from pathlib import Path
from typing import Optional, List, Dict, Any
from .base import BaseLLMClient, LLMConfig, GenerationConfig

logger = logging.getLogger(__name__)


class GeminiClient(BaseLLMClient):
    """Google Gemini LLM Client using google-genai SDK"""

    def __init__(self, config: LLMConfig):
        """
        Initialize Gemini client

        Args:
            config: LLMConfig with Gemini-specific settings
        """
        super().__init__(config)
        self.client = self._create_client()

    def _create_client(self):
        """Create and configure Gemini client"""
        try:
            from google import genai
            from google.genai import types
        except ImportError:
            raise ImportError(
                "google-genai is not installed. "
                "Install it with: pip install google-genai"
            )

        if self.config.use_vertex_ai:
            # Vertex AI configuration
            if not self.config.vertex_project:
                raise ValueError("vertex_project is required for Vertex AI")

            logger.info(
                f"Creating Gemini client for Vertex AI "
                f"(project={self.config.vertex_project}, "
                f"location={self.config.vertex_location or 'us-central1'})"
            )

            client = genai.Client(
                vertexai=True,
                project=self.config.vertex_project,
                location=self.config.vertex_location or "us-central1",
            )
        else:
            # Gemini Developer API configuration
            if not self.config.api_key:
                raise ValueError(
                    "api_key is required for Gemini Developer API. "
                    "Set GEMINI_API_KEY or GOOGLE_API_KEY environment variable"
                )

            logger.info("Creating Gemini client for Gemini Developer API")
            client = genai.Client(api_key=self.config.api_key)

        self._genai = genai
        self._types = types
        return client

    def generate(
        self, prompt: str, gen_config: Optional[GenerationConfig] = None, **kwargs
    ) -> str:
        """
        Generate text response from a single prompt

        Args:
            prompt: Input text prompt
            gen_config: GenerationConfig with temperature, max_tokens, etc.
            **kwargs: Additional parameters passed to generate_content

        Returns:
            Generated text response
        """
        config = gen_config or GenerationConfig()

        try:
            response = self.client.models.generate_content(
                model=self.model,
                contents=prompt,
                config=self._create_generation_config(config),
                **kwargs,
            )
            logger.info(f"Token usage for generate: {response.count_tokens}")
            if response.text:
                return response.text
            else:
                logger.warning("Empty response from Gemini")
                return ""

        except Exception as e:
            logger.error(f"Error generating content from Gemini: {e}")
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
            **kwargs: Additional parameters passed to generate_content

        Returns:
            Generated text response
        """
        config = gen_config or GenerationConfig()

        # Convert messages to Gemini format
        gemini_messages = self._convert_messages(messages)

        try:
            response = self.client.models.generate_content(
                model=self.model,
                contents=gemini_messages,
                config=self._create_generation_config(config),
                **kwargs,
            )
            logger.info(f"Token usage for chat: {response.count_tokens}")
            if response.text:
                return response.text
            else:
                logger.warning("Empty response from Gemini chat")
                return ""

        except Exception as e:
            logger.error(f"Error in Gemini chat: {e}")
            raise

    def stream_generate(
        self, prompt: str, gen_config: Optional[GenerationConfig] = None, **kwargs
    ):
        """
        Stream generated text response

        Args:
            prompt: Input text prompt
            gen_config: GenerationConfig with temperature, max_tokens, etc.
            **kwargs: Additional parameters passed to generate_content

        Yields:
            Text chunks of the response
        """
        config = gen_config or GenerationConfig()

        try:
            with self.client.models.generate_content(
                model=self.model,
                contents=prompt,
                config=self._create_generation_config(config),
                stream=True,
                **kwargs,
            ) as response:
                for chunk in response:
                    if chunk.text:
                        yield chunk.text

        except Exception as e:
            logger.error(f"Error streaming content from Gemini: {e}")
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
            **kwargs: Additional parameters passed to generate_content

        Yields:
            Text chunks of the response
        """
        config = gen_config or GenerationConfig()

        # Convert messages to Gemini format
        gemini_messages = self._convert_messages(messages)

        try:
            with self.client.models.generate_content(
                model=self.model,
                contents=gemini_messages,
                config=self._create_generation_config(config),
                stream=True,
                **kwargs,
            ) as response:
                for chunk in response:
                    if chunk.text:
                        yield chunk.text

        except Exception as e:
            logger.error(f"Error streaming chat from Gemini: {e}")
            raise

    def close(self) -> None:
        """Close client and cleanup resources"""
        if self.client:
            try:
                self.client.close()
                logger.info("Gemini client closed")
            except Exception as e:
                logger.error(f"Error closing Gemini client: {e}")

    def _upload_file(self, file_path: str):
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")

        try:
            uploaded_file = self.client.files.upload(file=str(path))
            logger.info(f"Uploaded file to Gemini: {file_path}")
            return uploaded_file
        except Exception as e:
            logger.error(f"Error uploading file to Gemini: {e}")
            raise

    def generate_file(
        self,
        file_path: str,
        prompt: Optional[str] = None,
        gen_config: Optional[GenerationConfig] = None,
        **kwargs,
    ) -> str:
        """Generate from local file using Gemini file upload support."""
        file_obj = self._upload_file(file_path)
        config = gen_config or GenerationConfig()

        contents = []
        if prompt:
            contents.append(prompt)
        contents.append(file_obj)

        try:
            response = self.client.models.generate_content(
                model=self.model,
                contents=contents,
                config=self._create_generation_config(config),
                **kwargs,
            )
            if response.text:
                return response.text
            logger.warning("Empty response from Gemini file generation")
            return ""
        except Exception as e:
            logger.error(f"Error generating from file in Gemini: {e}")
            raise

    def stream_generate_file(
        self,
        file_path: str,
        prompt: Optional[str] = None,
        gen_config: Optional[GenerationConfig] = None,
        **kwargs,
    ):
        """Stream generate from local file using Gemini file upload support."""
        file_obj = self._upload_file(file_path)
        config = gen_config or GenerationConfig()

        contents = []
        if prompt:
            contents.append(prompt)
        contents.append(file_obj)

        try:
            with self.client.models.generate_content(
                model=self.model,
                contents=contents,
                config=self._create_generation_config(config),
                stream=True,
                **kwargs,
            ) as response:
                for chunk in response:
                    if chunk.text:
                        yield chunk.text
        except Exception as e:
            logger.error(f"Error streaming from file in Gemini: {e}")
            raise

    def _create_generation_config(self, config: GenerationConfig) -> Dict[str, Any]:
        """
        Create generation configuration for Gemini

        Args:
            config: GenerationConfig with parameters

        Returns:
            Generation config dictionary
        """
        gen_config = {
            "temperature": config.temperature,
            "top_p": config.top_p,
        }

        if config.max_tokens:
            gen_config["max_output_tokens"] = config.max_tokens

        if config.top_k:
            gen_config["top_k"] = config.top_k

        return gen_config

    def _convert_messages(self, messages: List[Dict[str, str]]) -> List[Dict[str, str]]:
        """
        Convert message format to Gemini format

        Args:
            messages: Standard message format with 'role' and 'content'

        Returns:
            Messages in Gemini format
        """
        # Gemini uses 'user' and 'model' as role names
        gemini_messages = []
        for msg in messages:
            gemini_msg = {
                "role": (
                    "model"
                    if msg.get("role") == "assistant"
                    else msg.get("role", "user")
                ),
                "parts": [{"text": msg.get("content", "")}],
            }
            gemini_messages.append(gemini_msg)

        return gemini_messages
