import time
from typing import Callable, Optional, TypeVar

import httpx
from podcast_maker.core.logging_config import get_logger

try:
    from google.api_core import exceptions as google_exceptions
except Exception:  # pragma: no cover - optional dependency import guard
    google_exceptions = None


T = TypeVar("T")
logger = get_logger()


NETWORK_ERROR_TYPES: tuple[type[BaseException], ...] = (
    TimeoutError,
    ConnectionError,
    httpx.TimeoutException,
    httpx.NetworkError,
)

GOOGLE_TRANSIENT_ERROR_TYPES: tuple[type[BaseException], ...] = tuple(
    error_type
    for error_type in (
        getattr(google_exceptions, "DeadlineExceeded", None),
        getattr(google_exceptions, "ServiceUnavailable", None),
        getattr(google_exceptions, "InternalServerError", None),
        getattr(google_exceptions, "TooManyRequests", None),
        getattr(google_exceptions, "ResourceExhausted", None),
    )
    if isinstance(error_type, type)
) if google_exceptions is not None else ()


def is_transient_network_error(exc: BaseException) -> bool:
    if isinstance(exc, NETWORK_ERROR_TYPES):
        return True

    if GOOGLE_TRANSIENT_ERROR_TYPES and isinstance(exc, GOOGLE_TRANSIENT_ERROR_TYPES):
        return True

    return False


def retry_network_call(
    operation: str,
    call: Callable[[], T],
    *,
    retries: int = 3,
    initial_delay_seconds: float = 1.0,
    should_retry: Optional[Callable[[BaseException], bool]] = None,
) -> T:
    retry_predicate = should_retry or is_transient_network_error

    for attempt in range(retries + 1):
        try:
            return call()
        except Exception as exc:
            if attempt >= retries or not retry_predicate(exc):
                raise

            delay = initial_delay_seconds * (2**attempt)
            logger.warning(
                "network_call_retry operation=%s attempt=%d/%d retry_in=%.1fs error=%s",
                operation,
                attempt + 1,
                retries + 1,
                delay,
                exc,
            )
            time.sleep(delay)

    raise RuntimeError(f"{operation} retry loop exited unexpectedly")
