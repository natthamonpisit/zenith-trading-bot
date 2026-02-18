import pytest

from src.contracts.api_contracts import (
    APIResponse,
    CandidateDTO,
    KlineCandleDTO,
    KlineDTO,
    SignalDTO,
    WSEvent,
    build_error_response,
    build_success_response,
)
from src.contracts.error_codes import ErrorCode, build_api_error, is_retryable_code


def test_build_success_response_shape():
    payload = {"status": "ok"}
    res = build_success_response(payload, request_id="req-1")

    assert res.success is True
    assert res.data == payload
    assert res.error is None
    assert res.meta.request_id == "req-1"
    assert res.meta.version == "v1"


def test_build_error_response_shape():
    err = build_api_error(ErrorCode.E_VALIDATION_400, "symbol is required", {"field": "symbol"})
    res = build_error_response(err, request_id="req-2")

    assert res.success is False
    assert res.data is None
    assert res.error is not None
    assert res.error.code == ErrorCode.E_VALIDATION_400
    assert res.error.retryable is False


def test_api_response_rejects_success_with_error():
    err = build_api_error(ErrorCode.E_INTERNAL_500, "internal error")
    with pytest.raises(ValueError):
        APIResponse(
            success=True,
            data={"ok": True},
            error=err,
            meta={"request_id": "r-1", "ts": "2026-02-18T00:00:00Z", "version": "v1"},
        )


def test_kline_candle_validation():
    candle = KlineCandleDTO(time=1700000000, open=10, high=12, low=9, close=11, volume=100)
    assert candle.high == 12

    with pytest.raises(ValueError):
        KlineCandleDTO(time=1700000000, open=13, high=12, low=9, close=11, volume=100)


def test_kline_dto_minimal():
    dto = KlineDTO(
        symbol="BTC/USDT",
        tf="1m",
        candles=[{"time": 1700000000, "open": 10, "high": 12, "low": 9, "close": 11, "volume": 1}],
    )
    assert dto.symbol == "BTC/USDT"
    assert len(dto.candles) == 1


def test_candidate_and_signal_dto():
    c = CandidateDTO(
        symbol="ETH/USDT",
        screener_rank=1,
        liquidity_score=88.5,
        tradable=True,
        reject_reason=None,
    )
    s = SignalDTO(
        id="sig-1",
        symbol="ETH/USDT",
        signal_type="BUY",
        confidence=77.0,
        status="PENDING",
        reason_codes=["CONF_OK", "RSI_OK"],
    )
    assert c.tradable is True
    assert s.signal_type == "BUY"


def test_ws_event_contract():
    event = WSEvent(
        event_id="evt-1",
        event_type="chart.kline.BTCUSDT.1m",
        ts="2026-02-18T00:00:00Z",
        source="market_feed",
        payload={"price": 100000},
    )
    assert event.source == "market_feed"


def test_retryable_code_mapping():
    assert is_retryable_code(ErrorCode.E_DB_500) is True
    assert is_retryable_code(ErrorCode.E_VALIDATION_400) is False
