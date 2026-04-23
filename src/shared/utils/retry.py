"""Retry logic for LLM client requests"""

import asyncio
import logging
import time
from functools import wraps
from typing import Callable, TypeVar, Any

logger = logging.getLogger(__name__)

F = TypeVar("F", bound=Callable[..., Any])


class RetryConfig:
    """Configuration for retry behavior"""

    def __init__(
        self,
        max_retries: int = 3,
        initial_delay: float = 1.0,
        max_delay: float = 32.0,
        exponential_base: float = 2.0,
        jitter: bool = True,
    ):
        """
        Args:
            max_retries: Maximum number of retry attempts
            initial_delay: Initial delay in seconds between retries
            max_delay: Maximum delay in seconds between retries
            exponential_base: Base for exponential backoff calculation
            jitter: Whether to add random jitter to delays
        """
        self.max_retries = max_retries
        self.initial_delay = initial_delay
        self.max_delay = max_delay
        self.exponential_base = exponential_base
        self.jitter = jitter

    def get_delay(self, attempt: int) -> float:
        """Calculate delay for the given attempt number (0-indexed)"""
        delay = min(
            self.initial_delay * (self.exponential_base**attempt), self.max_delay
        )

        if self.jitter:
            import random

            # Add jitter: ±20% of the calculated delay
            jitter_amount = delay * 0.2 * (2 * random.random() - 1)
            delay = max(0, delay + jitter_amount)

        return delay


def is_retryable_error(error: Exception) -> bool:
    """
    Determine if an error is retryable

    Retryable errors:
    - Connection/timeout errors
    - Rate limit errors (429)
    - Server errors (5xx)
    - Temporary service unavailable errors
    """
    error_str = str(error).lower()
    error_type = type(error).__name__

    # Network and timeout errors
    if error_type in ("ConnectionError", "Timeout", "TimeoutError"):
        return True

    # Check for specific error patterns
    retryable_patterns = [
        "429",  # Rate limit
        "500",  # Internal server error
        "502",  # Bad gateway
        "503",  # Service unavailable
        "504",  # Gateway timeout
        "temporarily unavailable",
        "connection reset",
        "connection refused",
        "timeout",
        "deadline exceeded",
        "temporary failure",
        "unavailable",
    ]

    if any(pattern in error_str for pattern in retryable_patterns):
        return True

    return False


def retry_sync(config: RetryConfig = None) -> Callable:
    """
    Decorator for synchronous functions with retry logic

    Args:
        config: RetryConfig instance, uses defaults if None

    Returns:
        Decorator function
    """
    retry_config = config or RetryConfig()

    def decorator(func: F) -> F:
        @wraps(func)
        def wrapper(*args, **kwargs):
            last_error = None

            for attempt in range(retry_config.max_retries + 1):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    last_error = e

                    # Don't retry on non-retryable errors
                    if not is_retryable_error(e):
                        logger.debug(
                            f"Non-retryable error in {func.__name__}: {e}"
                        )
                        raise

                    # Don't retry if we've exhausted attempts
                    if attempt >= retry_config.max_retries:
                        logger.error(
                            f"Max retries ({retry_config.max_retries}) exceeded for {func.__name__}"
                        )
                        raise

                    delay = retry_config.get_delay(attempt)
                    logger.warning(
                        f"Attempt {attempt + 1}/{retry_config.max_retries + 1} failed for {func.__name__}: {e}. "
                        f"Retrying in {delay:.2f}s..."
                    )
                    time.sleep(delay)

            # Should never reach here, but just in case
            if last_error:
                raise last_error

        return wrapper

    return decorator


def retry_async(config: RetryConfig = None) -> Callable:
    """
    Decorator for async functions with retry logic

    Args:
        config: RetryConfig instance, uses defaults if None

    Returns:
        Decorator function
    """
    retry_config = config or RetryConfig()

    def decorator(func: F) -> F:
        @wraps(func)
        async def wrapper(*args, **kwargs):
            last_error = None

            for attempt in range(retry_config.max_retries + 1):
                try:
                    return await func(*args, **kwargs)
                except Exception as e:
                    last_error = e

                    # Don't retry on non-retryable errors
                    if not is_retryable_error(e):
                        logger.debug(
                            f"Non-retryable error in {func.__name__}: {e}"
                        )
                        raise

                    # Don't retry if we've exhausted attempts
                    if attempt >= retry_config.max_retries:
                        logger.error(
                            f"Max retries ({retry_config.max_retries}) exceeded for {func.__name__}"
                        )
                        raise

                    delay = retry_config.get_delay(attempt)
                    logger.warning(
                        f"Attempt {attempt + 1}/{retry_config.max_retries + 1} failed for {func.__name__}: {e}. "
                        f"Retrying in {delay:.2f}s..."
                    )
                    await asyncio.sleep(delay)

            # Should never reach here, but just in case
            if last_error:
                raise last_error

        return wrapper

    return decorator
