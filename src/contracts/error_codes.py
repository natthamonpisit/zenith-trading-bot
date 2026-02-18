"""
Standard error taxonomy for API and realtime channels.
"""
from __future__ import annotations

from enum import Enum
from typing import Any, Dict, Optional

from pydantic import BaseModel, Field


class ErrorCode(str, Enum):
    E_AUTH_401 = "E_AUTH_401"
    E_FORBIDDEN_403 = "E_FORBIDDEN_403"
    E_VALIDATION_400 = "E_VALIDATION_400"
    E_NOT_FOUND_404 = "E_NOT_FOUND_404"
    E_RATE_LIMIT_429 = "E_RATE_LIMIT_429"
    E_UPSTREAM_EXCHANGE_502 = "E_UPSTREAM_EXCHANGE_502"
    E_UPSTREAM_AI_503 = "E_UPSTREAM_AI_503"
    E_DB_500 = "E_DB_500"
    E_INTERNAL_500 = "E_INTERNAL_500"


_RETRYABLE_CODES = {
    ErrorCode.E_RATE_LIMIT_429,
    ErrorCode.E_UPSTREAM_EXCHANGE_502,
    ErrorCode.E_UPSTREAM_AI_503,
    ErrorCode.E_DB_500,
    ErrorCode.E_INTERNAL_500,
}


def is_retryable_code(code: ErrorCode) -> bool:
    """
    Returns True when the caller should retry the request safely.
    """
    return code in _RETRYABLE_CODES


class APIError(BaseModel):
    code: ErrorCode
    message: str = Field(min_length=1, max_length=500)
    retryable: bool
    details: dict[str, Any] = Field(default_factory=dict)


def build_api_error(code: ErrorCode, message: str, details: Optional[Dict[str, Any]] = None) -> APIError:
    """
    Build standardized API error payload.
    """
    return APIError(
        code=code,
        message=message,
        retryable=is_retryable_code(code),
        details=details or {},
    )
