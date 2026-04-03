"""Base LLM Client Interface"""

from abc import ABC, abstractmethod
from typing import Optional, List, Dict, Any
from dataclasses import dataclass
from pathlib import Path
import logging
import json
import mimetypes

logger = logging.getLogger(__name__)


@dataclass
class LLMConfig:
    """Configuration for LLM client initialization"""

    provider: str  # 'gemini' or 'ollama'
    api_key: Optional[str] = None
    model: str = "gemini-2.5-flash"

    # Ollama specific
    host: Optional[str] = None  # Default: http://localhost:11434

    # Gemini specific
    use_vertex_ai: bool = False
    vertex_project: Optional[str] = None
    vertex_location: Optional[str] = None

    # General options
    timeout: int = 30
    max_retries: int = 3


@dataclass
class GenerationConfig:
    """Configuration for generation/chat operations"""

    temperature: float = 0.7
    max_tokens: Optional[int] = None
    top_p: float = 0.9
    top_k: Optional[int] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary, excluding None values"""
        return {k: v for k, v in self.__dict__.items() if v is not None}


class BaseLLMClient(ABC):
    """Abstract base class for LLM clients"""

    def __init__(self, config: LLMConfig):
        """Initialize LLM client with configuration"""
        self.config = config
        self.model = config.model

    @abstractmethod
    def generate(
        self, prompt: str, gen_config: Optional[GenerationConfig] = None, **kwargs
    ) -> str:
        """
        Generate text response from a single prompt

        Args:
            prompt: Input text prompt
            gen_config: GenerationConfig with temperature, max_tokens, etc.
            **kwargs: Additional provider-specific parameters

        Returns:
            Generated text response
        """
        pass

    @abstractmethod
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
            **kwargs: Additional provider-specific parameters

        Returns:
            Generated text response
        """
        pass

    @abstractmethod
    def stream_generate(
        self, prompt: str, gen_config: Optional[GenerationConfig] = None, **kwargs
    ):
        """
        Stream generated text response

        Args:
            prompt: Input text prompt
            gen_config: GenerationConfig with temperature, max_tokens, etc.
            **kwargs: Additional provider-specific parameters

        Yields:
            Text chunks of the response
        """
        pass

    @abstractmethod
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
            **kwargs: Additional provider-specific parameters

        Yields:
            Text chunks of the response
        """
        pass

    @abstractmethod
    def close(self) -> None:
        """Close client and cleanup resources"""
        pass

    @abstractmethod
    def generate_file(
        self,
        file_path: str,
        prompt: Optional[str] = None,
        gen_config: Optional[GenerationConfig] = None,
        **kwargs,
    ) -> str:
        """
        Generate text from a file (binary or text) plus optional context prompt.
        Provider-specific implementations may upload/encode as needed.
        """
        raise NotImplementedError

    def generate_from_file(
        self, file_path: str, gen_config: Optional[GenerationConfig] = None, **kwargs
    ) -> str:
        """
        Generate text response from a file.

        If file is a text file, read text directly; otherwise delegate to generate_file.
        """
        path = Path(file_path)

        if not path.exists():
            raise FileNotFoundError(f"Prompt file not found: {file_path}")

        mime_type, _ = mimetypes.guess_type(file_path)
        # Treat explicit text types as plain text prompt input
        if mime_type and mime_type.startswith("text"):
            try:
                prompt = path.read_text(encoding="utf-8")
                logger.info(f"Loaded text prompt from {file_path}")
                return self.generate(prompt, gen_config, **kwargs)
            except Exception as e:
                logger.error(f"Error reading prompt file {file_path}: {e}")
                raise

        # For non-text files, use provider-specific file handling variant
        return self.generate_file(
            file_path, prompt=None, gen_config=gen_config, **kwargs
        )

    def chat_from_file(
        self,
        messages_file: str,
        gen_config: Optional[GenerationConfig] = None,
        **kwargs,
    ) -> str:
        """
        Generate chat response from messages file (JSON format)

        Args:
            messages_file: Path to JSON file with message history
            gen_config: GenerationConfig with temperature, max_tokens, etc.
            **kwargs: Additional provider-specific parameters

        Returns:
            Generated text response

        Raises:
            FileNotFoundError: If messages file does not exist
            ValueError: If file format is invalid
            IOError: If unable to read file
        """
        path = Path(messages_file)

        if not path.exists():
            raise FileNotFoundError(f"Messages file not found: {messages_file}")

        try:
            content = path.read_text(encoding="utf-8")
            messages = json.loads(content)

            if not isinstance(messages, list):
                raise ValueError("Messages file must contain a JSON array")

            logger.info(f"Loaded messages from {messages_file}")
            return self.chat(messages, gen_config, **kwargs)
        except FileNotFoundError:
            raise
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON in {messages_file}: {e}")
            raise ValueError(f"Invalid JSON format in {messages_file}") from e
        except Exception as e:
            logger.error(f"Error reading messages file {messages_file}: {e}")
            raise

    @abstractmethod
    def stream_generate_file(
        self,
        file_path: str,
        prompt: Optional[str] = None,
        gen_config: Optional[GenerationConfig] = None,
        **kwargs,
    ):
        """
        Stream generate from a file (binary or text) plus optional context prompt.
        """
        raise NotImplementedError

    def stream_generate_from_file(
        self, file_path: str, gen_config: Optional[GenerationConfig] = None, **kwargs
    ):
        """
        Stream generated text from a prompt file

        Args:
            file_path: Path to file containing the prompt
            gen_config: GenerationConfig with temperature, max_tokens, etc.
            **kwargs: Additional provider-specific parameters

        Yields:
            Text chunks of the response

        Raises:
            FileNotFoundError: If prompt file does not exist
            IOError: If unable to read file
        """
        path = Path(file_path)

        if not path.exists():
            raise FileNotFoundError(f"Prompt file not found: {file_path}")

        mime_type, _ = mimetypes.guess_type(file_path)
        if mime_type and mime_type.startswith("text"):
            try:
                prompt = path.read_text(encoding="utf-8")
                logger.info(f"Loaded prompt from {file_path}")
                yield from self.stream_generate(prompt, gen_config, **kwargs)
            except FileNotFoundError:
                raise
            except Exception as e:
                logger.error(f"Error reading prompt file {file_path}: {e}")
                raise
            return

        # binary or non-text file route
        yield from self.stream_generate_file(
            file_path, prompt=None, gen_config=gen_config, **kwargs
        )

    def stream_chat_from_file(
        self,
        messages_file: str,
        gen_config: Optional[GenerationConfig] = None,
        **kwargs,
    ):
        """
        Stream chat response from messages file (JSON format)

        Args:
            messages_file: Path to JSON file with message history
            gen_config: GenerationConfig with temperature, max_tokens, etc.
            **kwargs: Additional provider-specific parameters

        Yields:
            Text chunks of the response

        Raises:
            FileNotFoundError: If messages file does not exist
            ValueError: If file format is invalid
            IOError: If unable to read file
        """
        path = Path(messages_file)

        if not path.exists():
            raise FileNotFoundError(f"Messages file not found: {messages_file}")

        try:
            content = path.read_text(encoding="utf-8")
            messages = json.loads(content)

            if not isinstance(messages, list):
                raise ValueError("Messages file must contain a JSON array")

            logger.info(f"Loaded messages from {messages_file}")
            yield from self.stream_chat(messages, gen_config, **kwargs)
        except FileNotFoundError:
            raise
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON in {messages_file}: {e}")
            raise ValueError(f"Invalid JSON format in {messages_file}") from e
        except Exception as e:
            logger.error(f"Error reading messages file {messages_file}: {e}")
            raise

    def __enter__(self):
        """Context manager entry"""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit"""
        self.close()
