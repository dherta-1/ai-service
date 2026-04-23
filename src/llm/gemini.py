"""Google Gemini LLM Client Implementation"""

import logging
from pathlib import Path
from typing import Optional, List, Dict, Any
from .base import BaseLLMClient, LLMConfig, GenerationConfig
from google.genai import types
from src.shared.utils.retry import retry_sync, RetryConfig

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

    @retry_sync(RetryConfig(max_retries=3))
    def _generate_content(
        self, prompt: str, gen_config: GenerationConfig, **kwargs
    ) -> str:
        """Internal method with retry logic for generating content"""
        response = self.client.models.generate_content(
            model=self.model,
            contents=prompt,
            config=self._create_generation_config(gen_config),
            **kwargs,
        )
        logger.info(
            f"Token usage for chat: {response.usage_metadata.total_token_count}"
        )
        if response.text:
            return response.text
        logger.warning("Empty response from Gemini")
        return ""

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
            return self._generate_content(prompt, config, **kwargs)
        except Exception as e:
            logger.error(f"Error generating content from Gemini: {e}")
            raise

    @retry_sync(RetryConfig(max_retries=3))
    def _chat_content(
        self,
        gemini_messages: List[Dict[str, str]],
        gen_config: GenerationConfig,
        **kwargs,
    ) -> str:
        """Internal method with retry logic for chat"""
        response = self.client.models.generate_content(
            model=self.model,
            contents=gemini_messages,
            config=self._create_generation_config(gen_config),
            **kwargs,
        )
        logger.info(
            f"Token usage for chat: {response.usage_metadata.total_token_count}"
        )
        if response.text:
            return response.text
        logger.warning("Empty response from Gemini chat")
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
            **kwargs: Additional parameters passed to generate_content

        Returns:
            Generated text response
        """
        config = gen_config or GenerationConfig()

        # Convert messages to Gemini format
        gemini_messages = self._convert_messages(messages)

        try:
            return self._chat_content(gemini_messages, config, **kwargs)
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

    @retry_sync(RetryConfig(max_retries=3))
    def _embed_batch(self, texts: list[str], **kwargs) -> list[list[float]]:
        """Internal method with retry logic for embedding a batch of texts in one request"""
        config_kwargs = {"output_dimensionality": self.embedding_dimension}

        # task_type is only supported for gemini-embedding-001, not gemini-embedding-2
        if self.embedding_model == "gemini-embedding-001":
            config_kwargs["task_type"] = "SEMANTIC_SIMILARITY"

        response = self.client.models.embed_content(
            model=self.embedding_model,
            contents=texts,
            config=types.EmbedContentConfig(**config_kwargs),
            **kwargs,
        )

        # API returns embeddings (plural) as a list
        if response and hasattr(response, "embeddings") and response.embeddings:
            embeddings = []
            for embedding_obj in response.embeddings:
                # Extract the vector values
                if hasattr(embedding_obj, "values"):
                    embeddings.append(list(embedding_obj.values))
                else:
                    embeddings.append(list(embedding_obj))
            return embeddings

        logger.warning(f"Empty embedding response for batch of {len(texts)} texts")
        raise ValueError("Failed to generate embeddings")

    def embed(self, input: str | list[str], **kwargs) -> list[list[float]]:
        """
        Generate embeddings for input text(s) using Gemini

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
            # Send all texts in a single batch request
            embeddings = self._embed_batch(input, **kwargs)
            logger.info(f"Generated {len(embeddings)} embedding(s) using Gemini")
            return embeddings

        except Exception as e:
            logger.error(f"Error generating embeddings from Gemini: {e}")
            raise

    @retry_sync(RetryConfig(max_retries=3))
    def _upload_file_with_retry(self, file_path: str):
        """Internal method with retry logic for file upload"""
        return self.client.files.upload(file=file_path)

    def _upload_file(self, file_path: str):
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")

        try:
            uploaded_file = self._upload_file_with_retry(str(path))
            logger.info(f"Uploaded file to Gemini: {file_path}")
            return uploaded_file
        except Exception as e:
            logger.error(f"Error uploading file to Gemini: {e}")
            raise

    @retry_sync(RetryConfig(max_retries=3))
    def _generate_file_content(
        self, contents: list, gen_config: GenerationConfig, **kwargs
    ) -> str:
        """Internal method with retry logic for file generation"""
        response = self.client.models.generate_content(
            model=self.model,
            contents=contents,
            config=self._create_generation_config(gen_config),
            **kwargs,
        )
        logger.info(
            f"Token usage for chat: {response.usage_metadata.total_token_count}"
        )
        if response.text:
            return response.text
        logger.warning("Empty response from Gemini file generation")
        return ""

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
            return self._generate_file_content(contents, config, **kwargs)
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
