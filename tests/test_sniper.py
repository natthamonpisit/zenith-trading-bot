"""
Unit tests for SniperExecutor class (Order Execution Engine)

Tests cover:
- PAPER mode BUY execution
- PAPER mode SELL execution
- LIVE mode execution (mocked)
- Insufficient balance handling
- Position not found errors
- Thread-safe balance updates
"""

import pytest
from src.roles.job_executor import SniperExecutor
from unittest.mock import Mock, patch, MagicMock
import threading


@pytest.mark.unit
class TestSniperPaperModeBuy:
    """Test PAPER mode BUY execution"""
    
    def test_executes_buy_in_paper_mode(self, mock_db, mock_exchange, sample_trade_signal):
        """SniperExecutor should execute BUY order in PAPER mode"""
        # Arrange
        with patch('src.roles.job_executor.PriceSpy') as mock_spy_class:
            mock_spy = Mock()
            mock_spy.exchange = mock_exchange
            mock_spy_class.return_value = mock_spy
            
            sniper = SniperExecutor(spy_instance=mock_spy)
            sniper.db = mock_db
            
            # Mock config to return PAPER mode
            def mock_config_execute():
                return Mock(data=[{'value': 'PAPER'}])
            mock_db.table('bot_config').select('*').eq('key', 'TRADING_MODE').execute = mock_config_execute
            
            # Mock simulation wallet with sufficient balance
            def mock_wallet_execute():
                return Mock(data=[{'id': 1, 'balance': 10000.0}])
            mock_db.table('simulation_portfolio').select('*').eq('id', 1).execute = mock_wallet_execute
            
            # Mock ticker price
            mock_exchange.fetch_ticker.return_value = {'last': 50000.0}
            
            signal = sample_trade_signal.copy()
            signal['signal_type'] = 'BUY'
            signal['order_size'] = 500.0  # Buy with 500 USDT
            
            # Act
            success = sniper.execute_order(signal)
            
            # Assert
            assert success is True
            # Verify balance was updated (deducted)
            mock_db.table('simulation_portfolio').update.assert_called()
            # Verify position was created
            mock_db.table('positions').insert.assert_called()
    
    def test_rejects_buy_with_insufficient_paper_balance(self, mock_db, mock_exchange, sample_trade_signal):
        """SniperExecutor should reject BUY when PAPER balance insufficient"""
        # Arrange
        with patch('src.roles.job_executor.PriceSpy') as mock_spy_class:
            mock_spy = Mock()
            mock_spy.exchange = mock_exchange
            mock_spy_class.return_value = mock_spy
            
            sniper = SniperExecutor(spy_instance=mock_spy)
            sniper.db = mock_db
            
            # Mock PAPER mode
            mock_db.table('bot_config').select('*').eq('key', 'TRADING_MODE').execute = Mock(
                return_value=Mock(data=[{'value': 'PAPER'}])
            )
            
            # Mock wallet with LOW balance
            def mock_wallet_execute():
                return Mock(data=[{'id': 1, 'balance': 100.0}])  # Only 100 USDT
            mock_db.table('simulation_portfolio').select('*').eq('id', 1).execute = mock_wallet_execute
            
            mock_exchange.fetch_ticker.return_value = {'last': 50000.0}
            
            signal = sample_trade_signal.copy()
            signal['signal_type'] = 'BUY'
            signal['order_size'] = 500.0  # Try to buy 500 USDT worth
            
            # Act
            success = sniper.execute_order(signal)
            
            # Assert
            assert success is False
            # Verify signal was marked as FAILED
            mock_db.table('trade_signals').update.assert_called()


@pytest.mark.unit
class TestSniperPaperModeSell:
    """Test PAPER mode SELL execution"""
    
    def test_executes_sell_in_paper_mode(self, mock_db, mock_exchange, sample_trade_signal, create_mock_position):
        """SniperExecutor should execute SELL order in PAPER mode"""
        # Arrange
        with patch('src.roles.job_executor.PriceSpy') as mock_spy_class:
            mock_spy = Mock()
            mock_spy.exchange = mock_exchange
            mock_spy_class.return_value = mock_spy
            
            sniper = SniperExecutor(spy_instance=mock_spy)
            sniper.db = mock_db
            
            # Mock PAPER mode
            mock_db.table('bot_config').select('*').eq('key', 'TRADING_MODE').execute = Mock(
                return_value=Mock(data=[{'value': 'PAPER'}])
            )
            
            # Mock wallet
            mock_db.table('simulation_portfolio').select('*').eq('id', 1).execute = Mock(
                return_value=Mock(data=[{'id': 1, 'balance': 5000.0}])
            )
            
            # Mock open position exists
            position = create_mock_position(quantity=0.01, entry_avg=50000.0, is_sim=True)
            def mock_position_execute():
                return Mock(data=[position])
            
            # Setup chainable mock for position query
            pos_chain = Mock()
            pos_chain.eq.return_value = pos_chain
            pos_chain.order.return_value = pos_chain
            pos_chain.limit.return_value = pos_chain
            pos_chain.execute = mock_position_execute
            
            def table_mock(table_name):
                if table_name == 'positions':
                    result = Mock()
                    result.select.return_value = pos_chain
                    result.update.return_value = Mock(execute=Mock())
                    result.insert.return_value = Mock(execute=Mock())
                    return result
                return mock_db.table(table_name)
            
            mock_db.table = table_mock
            
            mock_exchange.fetch_ticker.return_value = {'last': 55000.0}  # Profit!
            
            signal = sample_trade_signal.copy()
            signal['signal_type'] = 'SELL'
            signal['order_size'] = 0
            
            # Act
            success = sniper.execute_order(signal)
            
            # Assert
            assert success is True
    
    def test_rejects_sell_when_no_position_exists(self, mock_db, mock_exchange, sample_trade_signal):
        """SniperExecutor should reject SELL when no position exists"""
        # Arrange
        with patch('src.roles.job_executor.PriceSpy') as mock_spy_class:
            mock_spy = Mock()
            mock_spy.exchange = mock_exchange
            mock_spy_class.return_value = mock_spy
            
            sniper = SniperExecutor(spy_instance=mock_spy)
            sniper.db = mock_db
            
            # Mock PAPER mode
            mock_db.table('bot_config').select('*').eq('key', 'TRADING_MODE').execute = Mock(
                return_value=Mock(data=[{'value': 'PAPER'}])
            )
            
            mock_db.table('simulation_portfolio').select('*').eq('id', 1).execute = Mock(
                return_value=Mock(data=[{'id': 1, 'balance': 5000.0}])
            )
            
            # Mock NO open position
            pos_chain = Mock()
            pos_chain.eq.return_value = pos_chain
            pos_chain.order.return_value = pos_chain
            pos_chain.limit.return_value = pos_chain
            pos_chain.execute = Mock(return_value=Mock(data=[]))  # Empty
            
            def table_mock(table_name):
                if table_name == 'positions':
                    result = Mock()
                    result.select.return_value = pos_chain
                    return result
                return mock_db.table(table_name)
            
            mock_db.table = table_mock
            
            mock_exchange.fetch_ticker.return_value = {'last': 55000.0}
            
            signal = sample_trade_signal.copy()
            signal['signal_type'] = 'SELL'
            
            # Act
            success = sniper.execute_order(signal)
            
            # Assert
            assert success is False


@pytest.mark.unit
class TestSniperLiveMode:
    """Test LIVE mode execution (mocked)"""
    
    def test_calls_exchange_api_in_live_mode(self, mock_db, mock_exchange, sample_trade_signal):
        """SniperExecutor should call real exchange API in LIVE mode"""
        # Arrange
        with patch('src.roles.job_executor.PriceSpy') as mock_spy_class:
            mock_spy = Mock()
            mock_spy.exchange = mock_exchange
            mock_spy.exchange.markets = {'BTC/USDT': {'id': 'BTCUSDT'}}
            mock_spy_class.return_value = mock_spy
            
            sniper = SniperExecutor(spy_instance=mock_spy)
            sniper.db = mock_db
            
            # Mock LIVE mode
            mock_db.table('bot_config').select('*').eq('key', 'TRADING_MODE').execute = Mock(
                return_value=Mock(data=[{'value': 'LIVE'}])
            )
            
            # Mock successful order creation
            mock_exchange.create_order.return_value = {
                'id': 'live_order_123',
                'price': 50000.0,
                'average': 50000.0,
                'amount': 0.01,
            }
            
            signal = sample_trade_signal.copy()
            signal['signal_type'] = 'BUY'
            signal['order_size'] = 500.0
            signal['is_sim'] = False
            
            # Act
            success = sniper.execute_order(signal)
            
            # Assert
            assert success is True
            # Verify exchange API was called
            mock_exchange.create_order.assert_called_once()
            # Verify position was created
            mock_db.table('positions').insert.assert_called()


@pytest.mark.unit  
class TestSniperThreadSafety:
    """Test thread-safe balance updates"""
    
    def test_concurrent_buys_dont_corrupt_balance(self, mock_db, mock_exchange):
        """Multiple concurrent BUY orders should not corrupt PAPER balance"""
        # This is a simplified test - full concurrency testing requires more setup
        # Just verify that the lock mechanism is in place
        
        with patch('src.roles.job_executor.PriceSpy') as mock_spy_class:
            with patch('src.roles.job_executor._sim_balance_lock') as mock_lock:
                mock_spy = Mock()
                mock_spy.exchange = mock_exchange
                mock_spy_class.return_value = mock_spy
                
                sniper = SniperExecutor(spy_instance=mock_spy)
                sniper.db = mock_db
                
                # Mock PAPER mode
                mock_db.table('bot_config').select('*').eq('key', 'TRADING_MODE').execute = Mock(
                    return_value=Mock(data=[{'value': 'PAPER'}])
                )
                
                mock_db.table('simulation_portfolio').select('*').eq('id', 1).execute = Mock(
                    return_value=Mock(data=[{'id': 1, 'balance': 10000.0}])
                )
                
                mock_exchange.fetch_ticker.return_value = {'last': 50000.0}
                
                signal = {
                    'id': 1,
                    'asset_id': 123,
                    'signal_type': 'BUY',
                    'order_size': 500.0,
                    'assets': {'symbol': 'BTC/USDT'},
                }
                
                # Act
                sniper.execute_order(signal)
                
                # Assert - Lock was used
                mock_lock.__enter__.assert_called()
                mock_lock.__exit__.assert_called()
