"""
API contract models and helpers.
"""

from src.contracts.api_contracts import (
    APIResponse,
    CandidateDTO,
    EnvelopeMeta,
    KlineCandleDTO,
    KlineDTO,
    SignalDTO,
    SummaryDTO,
    WSEvent,
    build_error_response,
    build_success_response,
)
from src.contracts.error_codes import APIError, ErrorCode, build_api_error, is_retryable_code

__all__ = [
    "APIError",
    "APIResponse",
    "CandidateDTO",
    "EnvelopeMeta",
    "ErrorCode",
    "KlineCandleDTO",
    "KlineDTO",
    "SignalDTO",
    "SummaryDTO",
    "WSEvent",
    "build_api_error",
    "build_error_response",
    "build_success_response",
    "is_retryable_code",
]
