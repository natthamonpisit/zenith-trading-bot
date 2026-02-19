"""
P1 API and WebSocket contracts.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Literal, Optional
from uuid import uuid4

from pydantic import BaseModel, Field, model_validator

from src.contracts.error_codes import APIError


class EnvelopeMeta(BaseModel):
    request_id: str = Field(min_length=1)
    ts: datetime
    version: str = Field(default="v1", min_length=2, max_length=10)


class APIResponse(BaseModel):
    success: bool
    data: Optional[Any] = None
    error: Optional[APIError] = None
    meta: EnvelopeMeta

    @model_validator(mode="after")
    def validate_envelope(self):
        if self.success and self.error is not None:
            raise ValueError("success response must not include error")
        if not self.success and self.error is None:
            raise ValueError("error response must include error object")
        return self


class KlineCandleDTO(BaseModel):
    time: int = Field(ge=0, description="Unix timestamp in seconds")
    open: float = Field(gt=0)
    high: float = Field(gt=0)
    low: float = Field(gt=0)
    close: float = Field(gt=0)
    volume: float = Field(ge=0)

    @model_validator(mode="after")
    def validate_ohlc(self):
        if self.high < self.low:
            raise ValueError("high must be greater than or equal to low")
        if not (self.low <= self.open <= self.high):
            raise ValueError("open must be between low and high")
        if not (self.low <= self.close <= self.high):
            raise ValueError("close must be between low and high")
        return self


class KlineDTO(BaseModel):
    symbol: str = Field(min_length=3, max_length=30)
    tf: str = Field(min_length=2, max_length=5)
    candles: list[KlineCandleDTO] = Field(default_factory=list)


class SummaryDTO(BaseModel):
    equity: float
    daily_pnl: float
    drawdown_pct: float
    open_positions: int = Field(ge=0)
    win_rate: float = Field(ge=0, le=100)
    bot_status: str = Field(min_length=3, max_length=30)
    bot_status_detail: Optional[str] = Field(default=None, max_length=300)
    heartbeat_age_sec: Optional[int] = Field(default=None, ge=0)
    last_heartbeat_at: Optional[str] = Field(default=None, min_length=1, max_length=64)
    uptime_sec: Optional[int] = Field(default=None, ge=0)


class CandidateDTO(BaseModel):
    symbol: str = Field(min_length=3, max_length=30)
    screener_rank: int = Field(ge=1)
    liquidity_score: float = Field(ge=0, le=100)
    tradable: bool
    reject_reason: Optional[str] = Field(default=None, max_length=300)


class SignalDTO(BaseModel):
    id: str = Field(min_length=1, max_length=64)
    symbol: str = Field(min_length=3, max_length=30)
    signal_type: Literal["BUY", "SELL", "WAIT", "HOLD"]
    confidence: float = Field(ge=0, le=100)
    status: str = Field(min_length=3, max_length=30)
    reason_codes: list[str] = Field(default_factory=list)


class WSEvent(BaseModel):
    event_id: str = Field(min_length=1)
    event_type: str = Field(min_length=3, max_length=80)
    ts: datetime
    source: str = Field(min_length=2, max_length=50)
    payload: Dict[str, Any] = Field(default_factory=dict)


def build_success_response(data: Any, request_id: Optional[str] = None, version: str = "v1") -> APIResponse:
    """
    Create a standardized success response payload.
    """
    return APIResponse(
        success=True,
        data=data,
        error=None,
        meta=EnvelopeMeta(
            request_id=request_id or str(uuid4()),
            ts=datetime.now(tz=timezone.utc),
            version=version,
        ),
    )


def build_error_response(error: APIError, request_id: Optional[str] = None, version: str = "v1") -> APIResponse:
    """
    Create a standardized error response payload.
    """
    return APIResponse(
        success=False,
        data=None,
        error=error,
        meta=EnvelopeMeta(
            request_id=request_id or str(uuid4()),
            ts=datetime.now(tz=timezone.utc),
            version=version,
        ),
    )
