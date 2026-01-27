"""
Pytest configuration and shared fixtures for Zenith Trading Bot tests.

This module provides:
- Mock database client
- Mock CCXT exchange
- Sample test data generators
- Shared fixtures for all tests
"""

import pytest
from unittest.mock import Mock, MagicMock
import pandas as pd
from datetime import datetime, timezone


# ===========================
# Mock Database Client
# ===========================

@pytest.fixture
def mock_db():
    """Mock Supabase database client"""
    db = Mock()
    
    # Mock table() method to return a chainable query builder
    table_mock = Mock()
    table_mock.select = Mock(return_value=table_mock)
    table_mock.insert = Mock(return_value=table_mock)
    table_mock.update = Mock(return_value=table_mock)
    table_mock.delete = Mock(return_value=table_mock)
    table_mock.eq = Mock(return_value=table_mock)
    table_mock.gte = Mock(return_value=table_mock)
    table_mock.lte = Mock(return_value=table_mock)
    table_mock.order = Mock(return_value=table_mock)
    table_mock.limit = Mock(return_value=table_mock)
    table_mock.execute = Mock(return_value=Mock(data=[]))
    
    db.table = Mock(return_value=table_mock)
    
    return db


@pytest.fixture
def mock_db_with_config(mock_db):
    """Mock database with bot_config table populated"""
    def get_config_value(key):
        """Helper to return config values"""
        config_values = {
            'TRADING_MODE': 'PAPER',
            'RSI_THRESHOLD': '75',
            'AI_CONF_THRESHOLD': '60',
            'MAX_OPEN_POSITIONS': '5',
            'POSITION_SIZE_PCT': '5.0',
            'MAX_RISK_PER_TRADE': '10.0',
            'ENABLE_EMA_TREND': 'false',
            'ENABLE_MACD_MOMENTUM': 'false',
            'MIN_VOLUME': '50000',
            'TRADING_UNIVERSE': 'ALL',
            'TIMEFRAME': '1h',
            'TRAILING_STOP_ENABLED': 'true',
            'TRAILING_STOP_PCT': '3.0',
            'MIN_PROFIT_TO_TRAIL_PCT': '1.0',
        }
        return config_values.get(key, '')
    
    # Override table() for bot_config queries
    original_table = mock_db.table
    
    def table_selector(table_name):
        table_mock = original_table(table_name)
        
        if table_name == 'bot_config':
            def execute_config():
                # Check if eq() was called with 'key' parameter
                if hasattr(table_mock.eq, 'call_args') and table_mock.eq.call_args:
                    key = table_mock.eq.call_args[0][1]
                    value = get_config_value(key)
                    return Mock(data=[{'key': key, 'value': value}])
                # Return all config if no filter
                return Mock(data=[
                    {'key': k, 'value': v} for k, v in get_config_value.__code__.co_consts[1].items()
                ])
            
            table_mock.execute = Mock(side_effect=execute_config)
        
        return table_mock
    
    mock_db.table = Mock(side_effect=table_selector)
    return mock_db


# ===========================
# Mock CCXT Exchange
# ===========================

@pytest.fixture
def mock_exchange():
    """Mock CCXT exchange (Binance)"""
    exchange = Mock()
    exchange.id = 'binance'
    exchange.markets = {
        'BTC/USDT': {
            'id': 'BTCUSDT',
            'symbol': 'BTC/USDT',
            'base': 'BTC',
            'quote': 'USDT',
            'active': True,
            'type': 'spot',
        },
        'ETH/USDT': {
            'id': 'ETHUSDT',
            'symbol': 'ETH/USDT',
            'base': 'ETH',
            'quote': 'USDT',
            'active': True,
            'type': 'spot',
        }
    }
    
    # Mock methods
    exchange.fetch_ticker = Mock(return_value={
        'symbol': 'BTC/USDT',
        'last': 50000.0,
        'bid': 49990.0,
        'ask': 50010.0,
        'baseVolume': 1000.0,
        'quoteVolume': 50000000.0,
    })
    
    exchange.fetch_balance = Mock(return_value={
        'total': {'USDT': 10000.0, 'BTC': 0.5},
        'free': {'USDT': 10000.0, 'BTC': 0.5},
        'used': {'USDT': 0.0, 'BTC': 0.0},
    })
    
    exchange.create_order = Mock(return_value={
        'id': 'test_order_123',
        'symbol': 'BTC/USDT',
        'type': 'market',
        'side': 'buy',
        'price': 50000.0,
        'average': 50000.0,
        'amount': 0.01,
        'filled': 0.01,
        'status': 'closed',
    })
    
    exchange.cost_to_precision = Mock(side_effect=lambda symbol, cost: round(cost, 2))
    exchange.amount_to_precision = Mock(side_effect=lambda symbol, amount: round(amount, 8))
    
    return exchange


# ===========================
# Sample Data Generators
# ===========================

@pytest.fixture
def sample_ohlcv_data():
    """Generate sample OHLCV data for testing"""
    dates = pd.date_range(start='2024-01-01', periods=100, freq='1H')
    data = {
        'timestamp': dates,
        'open': [50000 + i * 10 for i in range(100)],
        'high': [50100 + i * 10 for i in range(100)],
        'low': [49900 + i * 10 for i in range(100)],
        'close': [50050 + i * 10 for i in range(100)],
        'volume': [1000 + i for i in range(100)],
    }
    return pd.DataFrame(data)


@pytest.fixture
def sample_technical_data():
    """Sample technical indicators for Judge testing"""
    return {
        'rsi': 65.5,
        'close': 50000.0,
        'ema_50': 49500.0,
        'macd': 0.0012,
        'macd_signal': 0.0010,
        'atr': 500.0,
    }


@pytest.fixture
def sample_ai_analysis():
    """Sample AI analysis output"""
    return {
        'confidence': 75,
        'recommendation': 'BUY',
        'reasoning': 'Strong uptrend with bullish momentum',
        'sentiment_score': 0.75,
    }


@pytest.fixture
def sample_trade_signal():
    """Sample trade signal for testing"""
    return {
        'id': 1,
        'asset_id': 123,
        'signal_type': 'BUY',
        'entry_target': 50000.0,
        'status': 'PENDING',
        'judge_reason': 'AI Agreed (Conf: 75%) + Tech Clean',
        'is_sim': True,
        'order_size': 500.0,
        'assets': {'symbol': 'BTC/USDT'},
    }


@pytest.fixture
def sample_candidates():
    """Sample market scan candidates"""
    return [
        {'symbol': 'BTC/USDT', 'volume': 100000000},
        {'symbol': 'ETH/USDT', 'volume': 80000000},
        {'symbol': 'SOL/USDT', 'volume': 60000000},
        {'symbol': 'BNB/USDT', 'volume': 55000000},
        {'symbol': 'XRP/USDT', 'volume': 45000000},
    ]


# ===========================
# Helper Functions
# ===========================

@pytest.fixture
def create_mock_position():
    """Factory to create mock position data"""
    def _create(
        asset_id=123,
        symbol='BTC/USDT',
        side='LONG',
        entry_avg=50000.0,
        quantity=0.01,
        is_open=True,
        is_sim=True,
    ):
        return {
            'id': 1,
            'asset_id': asset_id,
            'side': side,
            'entry_avg': entry_avg,
            'quantity': quantity,
            'is_open': is_open,
            'is_sim': is_sim,
            'highest_price_seen': entry_avg,
            'trailing_stop_price': None,
            'assets': {'symbol': symbol},
            'created_at': datetime.now(timezone.utc).isoformat(),
        }
    return _create


# ===========================
# Pytest Markers
# ===========================

def pytest_configure(config):
    """Configure custom pytest markers"""
    config.addinivalue_line("markers", "unit: Unit tests")
    config.addinivalue_line("markers", "integration: Integration tests")
    config.addinivalue_line("markers", "slow: Tests that take a long time")
