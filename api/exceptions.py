"""Centralized Redis exception mapping for API and pipeline layers."""

from __future__ import annotations

from fastapi import HTTPException
from redis.exceptions import ConnectionError as RedisConnectionError
from redis.exceptions import ResponseError, TimeoutError

from core.logging import get_logger


logger = get_logger(__name__)


class RedisOperationError(Exception):
    """Raised when a Redis operation fails and needs API-level handling."""


def handle_redis_error(e: Exception, context: str) -> None:
    logger.exception(
        "redis_operation_error",
        extra={
            "operation": context,
            "error_type": type(e).__name__,
            "error": str(e),
        },
    )

    if isinstance(e, RedisConnectionError):
        raise HTTPException(status_code=503, detail="Redis unavailable") from e
    if isinstance(e, TimeoutError):
        raise HTTPException(status_code=504, detail="Redis timeout") from e
    if isinstance(e, ResponseError):
        raise HTTPException(status_code=500, detail="Redis operation failed") from e
    raise HTTPException(status_code=500, detail="Internal error") from e