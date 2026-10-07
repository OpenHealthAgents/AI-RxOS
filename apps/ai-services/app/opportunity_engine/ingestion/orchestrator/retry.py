from __future__ import annotations

import asyncio
import logging
import random
from typing import Any, Awaitable, Callable, Optional, Tuple

from .models import RetryPolicy

logger = logging.getLogger(__name__)


class NonRetryableIngestionError(Exception):
    """Raised for fatal errors that must NOT be retried (e.g., schema poison pills)."""
    pass


class IngestionRetryExecutor:
    """
    Asynchronous retry executor implementing exponential backoff with jitter
    and intelligent transient failure detection.
    """

    DEFAULT_TRANSIENT_EXCEPTIONS = (
        asyncio.TimeoutError,
        ConnectionResetError,
        ConnectionRefusedError,
        OSError,
    )

    @classmethod
    def is_transient_error(cls, exc: Exception) -> bool:
        """Determines whether an exception is considered transient and safe to retry."""
        if isinstance(exc, NonRetryableIngestionError):
            return False

        if isinstance(exc, cls.DEFAULT_TRANSIENT_EXCEPTIONS):
            return True

        # Check for HTTP status codes in standard exception attributes
        status_code = getattr(exc, "status_code", None) or getattr(exc, "status", None)
        if status_code in (429, 502, 503, 504):
            return True

        # Check message keywords
        msg = str(exc).lower()
        if any(term in msg for term in ("timeout", "rate limit", "temporarily unavailable", "connection reset", "retry")):
            return True

        # By default in ingestion pipelines, uncaught operational exceptions are retried
        # up to the configured limit unless explicitly flagged as NonRetryable
        return True

    @classmethod
    def calculate_backoff(
        cls,
        attempt: int,
        policy: RetryPolicy,
    ) -> float:
        """Computes exponential backoff with optional full jitter."""
        base_delay = policy.initial_backoff_seconds * (policy.backoff_multiplier ** attempt)
        capped_delay = min(policy.max_backoff_seconds, base_delay)

        if policy.jitter:
            # Full jitter: random uniform between 0 and capped delay
            return random.uniform(0.5 * capped_delay, capped_delay)
        return capped_delay

    @classmethod
    async def execute_with_retry(
        cls,
        operation: Callable[..., Awaitable[Any]],
        *args: Any,
        policy: Optional[RetryPolicy] = None,
        is_transient_fn: Optional[Callable[[Exception], bool]] = None,
        on_retry_callback: Optional[Callable[[int, Exception, float], None]] = None,
        **kwargs: Any,
    ) -> Tuple[Any, int]:
        """
        Executes an asynchronous operation with retry policy.
        Returns: (result: Any, retry_count: int)
        Raises the last encountered exception if all retries are exhausted.
        """
        active_policy = policy or RetryPolicy()
        is_transient = is_transient_fn or cls.is_transient_error

        last_exception: Optional[Exception] = None
        retries_used = 0

        for attempt in range(active_policy.max_retries + 1):
            try:
                if asyncio.iscoroutinefunction(operation):
                    result = await operation(*args, **kwargs)
                else:
                    result = operation(*args, **kwargs)
                    if asyncio.iscoroutine(result):
                        result = await result
                return result, retries_used
            except Exception as e:
                last_exception = e
                if attempt >= active_policy.max_retries:
                    logger.warning(
                        "Max retries (%d) exhausted for operation: %s",
                        active_policy.max_retries,
                        e,
                    )
                    break

                if not is_transient(e):
                    logger.warning(
                        "Encountered non-retryable error on attempt %d: %s",
                        attempt + 1,
                        e,
                    )
                    break

                retries_used += 1
                backoff_delay = cls.calculate_backoff(attempt, active_policy)
                logger.info(
                    "Retry attempt %d/%d after %.2fs delay due to: %s",
                    attempt + 1,
                    active_policy.max_retries,
                    backoff_delay,
                    e,
                )

                if on_retry_callback:
                    try:
                        on_retry_callback(attempt + 1, e, backoff_delay)
                    except Exception as cb_err:
                        logger.error("Error in on_retry_callback: %s", cb_err)

                await asyncio.sleep(backoff_delay)

        if last_exception:
            raise last_exception
        raise RuntimeError("Operation failed with unknown state in IngestionRetryExecutor.")
