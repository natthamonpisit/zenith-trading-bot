"""
Unit tests for Judge class (Risk Management & Position Sizing)

Tests cover:
- RSI threshold rejection
- Position limit enforcement (PAPER/LIVE separate)
- Position sizing calculations
- Trend checks (EMA)
- Momentum checks (MACD)
- AI confidence threshold
- SELL order bypass (no position limit)
"""

import pytest
from src.roles.job_analysis import Judge, TradeDecision
from unittest.mock import Mock, patch


@pytest.mark.unit
class TestJudgeRSIVeto:
    """Test RSI veto logic"""
    
    def test_rejects_buy_when_rsi_too_high(self, mock_db_with_config, sample_ai_analysis, sample_technical_data):
        """Judge should REJECT BUY when RSI > threshold"""
        # Arrange
        judge = Judge()
        judge.db = mock_db_with_config
        judge.config = judge._load_config()
        
        ai_data = sample_ai_analysis.copy()
        ai_data['recommendation'] = 'BUY'
        
        tech_data = sample_technical_data.copy()
        tech_data['rsi'] = 80  # Above threshold (75)
        
        # Act
        decision = judge.evaluate(ai_data, tech_data, portfolio_balance=10000, is_sim=True)
        
        # Assert
        assert decision.decision == "REJECTED"
        assert "RSI" in decision.reason
        assert decision.size == 0
    
    def test_allows_buy_when_rsi_acceptable(self, mock_db_with_config, sample_ai_analysis, sample_technical_data):
        """Judge should APPROVE BUY when RSI is acceptable"""
        # Arrange
        judge = Judge()
        judge.db = mock_db_with_config
        judge.config = judge._load_config()
        
        ai_data = sample_ai_analysis.copy()
        ai_data['recommendation'] = 'BUY'
        ai_data['confidence'] = 80
        
        tech_data = sample_technical_data.copy()
        tech_data['rsi'] = 60  # Below threshold (75)
        
        # Act
        decision = judge.evaluate(ai_data, tech_data, portfolio_balance=10000, is_sim=True)
        
        # Assert
        assert decision.decision == "APPROVED"
        assert decision.size > 0


@pytest.mark.unit
class TestJudgePositionLimits:
    """Test position limit enforcement"""
    
    def test_rejects_buy_when_max_positions_reached_paper(self, mock_db_with_config, sample_ai_analysis, sample_technical_data):
        """Judge should REJECT BUY when max PAPER positions reached"""
        # Arrange
        judge = Judge()
        judge.db = mock_db_with_config
        judge.config = judge._load_config()
        
        # Mock 5 open PAPER positions (max is 5)
        mock_positions = Mock(data=[{'id': i} for i in range(5)])
        judge.db.table('positions').select('id').eq('is_open', True).eq('is_sim', True).execute = Mock(return_value=mock_positions)
        
        ai_data = sample_ai_analysis.copy()
        ai_data['recommendation'] = 'BUY'
        ai_data['confidence'] = 80
        
        tech_data = sample_technical_data.copy()
        tech_data['rsi'] = 60
        
        # Act
        decision = judge.evaluate(ai_data, tech_data, portfolio_balance=10000, is_sim=True)
        
        # Assert
        assert decision.decision == "REJECTED"
        assert "Position Limit" in decision.reason
        assert "5/5" in decision.reason
    
    def test_allows_buy_when_under_position_limit(self, mock_db_with_config, sample_ai_analysis, sample_technical_data):
        """Judge should APPROVE BUY when under position limit"""
        # Arrange
        judge = Judge()
        judge.db = mock_db_with_config
        judge.config = judge._load_config()
        
        # Mock 3 open positions (max is 5)
        mock_positions = Mock(data=[{'id': i} for i in range(3)])
        judge.db.table('positions').select('id').eq('is_open', True).eq('is_sim', True).execute = Mock(return_value=mock_positions)
        
        ai_data = sample_ai_analysis.copy()
        ai_data['recommendation'] = 'BUY'
        ai_data['confidence'] = 80
        
        tech_data = sample_technical_data.copy()
        tech_data['rsi'] = 60
        
        # Act
        decision = judge.evaluate(ai_data, tech_data, portfolio_balance=10000, is_sim=True)
        
        # Assert
        assert decision.decision == "APPROVED"
        assert decision.size > 0
    
    def test_allows_sell_regardless_of_position_limit(self, mock_db_with_config, sample_ai_analysis, sample_technical_data):
        """Judge should APPROVE SELL even when at max positions"""
        # Arrange
        judge = Judge()
        judge.db = mock_db_with_config
        judge.config = judge._load_config()
        
        # Mock 5 open positions (at max)
        mock_positions = Mock(data=[{'id': i} for i in range(5)])
        judge.db.table('positions').select('id').eq('is_open', True).eq('is_sim', True).execute = Mock(return_value=mock_positions)
        
        ai_data = sample_ai_analysis.copy()
        ai_data['recommendation'] = 'SELL'
        ai_data['confidence'] = 80
        
        tech_data = sample_technical_data.copy()
        
        # Act
        decision = judge.evaluate(ai_data, tech_data, portfolio_balance=10000, is_sim=True)
        
        # Assert
        assert decision.decision == "APPROVED"
        # SELL bypasses position limit check


@pytest.mark.unit
class TestJudgePositionSizing:
    """Test position sizing calculations"""
    
    def test_calculates_correct_position_size(self, mock_db_with_config, sample_ai_analysis, sample_technical_data):
        """Judge should calculate position size based on POSITION_SIZE_PCT"""
        # Arrange
        judge = Judge()
        judge.db = mock_db_with_config
        judge.config = judge._load_config()
        
        # Mock no open positions
        judge.db.table('positions').select('id').eq('is_open', True).eq('is_sim', True).execute = Mock(return_value=Mock(data=[]))
        
        ai_data = sample_ai_analysis.copy()
        ai_data['recommendation'] = 'BUY'
        ai_data['confidence'] = 80
        
        tech_data = sample_technical_data.copy()
        tech_data['rsi'] = 60
        
        portfolio_balance = 10000.0
        
        # Act
        decision = judge.evaluate(ai_data, tech_data, portfolio_balance=portfolio_balance, is_sim=True)
        
        # Assert
        expected_size = 10000 * 0.05  # 5% of 10000 = 500
        assert decision.decision == "APPROVED"
        assert decision.size == expected_size
    
    def test_respects_max_risk_per_trade(self, mock_db_with_config, sample_ai_analysis, sample_technical_data):
        """Judge should not exceed MAX_RISK_PER_TRADE"""
        # Arrange
        judge = Judge()
        judge.db = mock_db_with_config
        
        # Override config to make POSITION_SIZE_PCT > MAX_RISK_PER_TRADE
        judge.config = {
            'POSITION_SIZE_PCT': '15.0',  # 15%
            'MAX_RISK_PER_TRADE': '10.0',  # 10% (lower)
            'RSI_THRESHOLD': '75',
            'AI_CONF_THRESHOLD': '60',
            'MAX_OPEN_POSITIONS': '5',
        }
        
        # Mock no open positions
        judge.db.table('positions').select('id').eq('is_open', True).eq('is_sim', True).execute = Mock(return_value=Mock(data=[]))
        
        ai_data = sample_ai_analysis.copy()
        ai_data['recommendation'] = 'BUY'
        ai_data['confidence'] = 80
        
        tech_data = sample_technical_data.copy()
        tech_data['rsi'] = 60
        
        portfolio_balance = 10000.0
        
        # Act
        decision = judge.evaluate(ai_data, tech_data, portfolio_balance=portfolio_balance, is_sim=True)
        
        # Assert
        # Should use MAX_RISK (10%) not POSITION_SIZE (15%)
        expected_size = 10000 * 0.10  # 10% of 10000 = 1000
        assert decision.decision == "APPROVED"
        assert decision.size == expected_size


@pytest.mark.unit
class TestJudgeTrendChecks:
    """Test EMA trend checks"""
    
    def test_rejects_buy_when_price_below_ema50_if_enabled(self, mock_db_with_config, sample_ai_analysis, sample_technical_data):
        """Judge should REJECT BUY when price < EMA50 (if trend check enabled)"""
        # Arrange
        judge = Judge()
        judge.db = mock_db_with_config
        judge.config = judge._load_config()
        judge.config['ENABLE_EMA_TREND'] = 'true'  # Enable trend check
        
        # Mock no open positions
        judge.db.table('positions').select('id').eq('is_open', True).eq('is_sim', True).execute = Mock(return_value=Mock(data=[]))
        
        ai_data = sample_ai_analysis.copy()
        ai_data['recommendation'] = 'BUY'
        ai_data['confidence'] = 80
        
        tech_data = sample_technical_data.copy()
        tech_data['rsi'] = 60
        tech_data['close'] = 49000.0  # Below EMA50 (49500)
        tech_data['ema_50'] = 49500.0
        
        # Act
        decision = judge.evaluate(ai_data, tech_data, portfolio_balance=10000, is_sim=True)
        
        # Assert
        assert decision.decision == "REJECTED"
        assert "Trend Veto" in decision.reason
        assert "EMA50" in decision.reason


@pytest.mark.unit
class TestJudgeMomentumChecks:
    """Test MACD momentum checks"""
    
    def test_rejects_buy_when_macd_bearish_if_enabled(self, mock_db_with_config, sample_ai_analysis, sample_technical_data):
        """Judge should REJECT BUY when MACD < Signal (if momentum check enabled)"""
        # Arrange
        judge = Judge()
        judge.db = mock_db_with_config
        judge.config = judge._load_config()
        judge.config['ENABLE_MACD_MOMENTUM'] = 'true'  # Enable momentum check
        
        # Mock no open positions
        judge.db.table('positions').select('id').eq('is_open', True).eq('is_sim', True).execute = Mock(return_value=Mock(data=[]))
        
        ai_data = sample_ai_analysis.copy()
        ai_data['recommendation'] = 'BUY'
        ai_data['confidence'] = 80
        
        tech_data = sample_technical_data.copy()
        tech_data['rsi'] = 60
        tech_data['macd'] = 0.0008  # Below signal
        tech_data['macd_signal'] = 0.0012
        
        # Act
        decision = judge.evaluate(ai_data, tech_data, portfolio_balance=10000, is_sim=True)
        
        # Assert
        assert decision.decision == "REJECTED"
        assert "Momentum Veto" in decision.reason
        assert "MACD" in decision.reason


@pytest.mark.unit
class TestJudgeAIConfidence:
    """Test AI confidence threshold"""
    
    def test_rejects_low_confidence_signals(self, mock_db_with_config, sample_ai_analysis, sample_technical_data):
        """Judge should REJECT when AI confidence < threshold"""
        # Arrange
        judge = Judge()
        judge.db = mock_db_with_config
        judge.config = judge._load_config()
        
        # Mock no open positions
        judge.db.table('positions').select('id').eq('is_open', True).eq('is_sim', True).execute = Mock(return_value=Mock(data=[]))
        
        ai_data = sample_ai_analysis.copy()
        ai_data['recommendation'] = 'BUY'
        ai_data['confidence'] = 50  # Below threshold (60)
        
        tech_data = sample_technical_data.copy()
        tech_data['rsi'] = 60
        
        # Act
        decision = judge.evaluate(ai_data, tech_data, portfolio_balance=10000, is_sim=True)
        
        # Assert
        assert decision.decision == "REJECTED"
        assert "AI Uncertainty" in decision.reason
    
    def test_rejects_wait_recommendation(self, mock_db_with_config, sample_ai_analysis, sample_technical_data):
        """Judge should REJECT WAIT recommendations"""
        # Arrange
        judge = Judge()
        judge.db = mock_db_with_config
        judge.config = judge._load_config()
        
        ai_data = sample_ai_analysis.copy()
        ai_data['recommendation'] = 'WAIT'
        ai_data['confidence'] = 80
        
        tech_data = sample_technical_data.copy()
        
        # Act
        decision = judge.evaluate(ai_data, tech_data, portfolio_balance=10000, is_sim=True)
        
        # Assert
        assert decision.decision == "REJECTED"
        assert "WAIT" in decision.reason
