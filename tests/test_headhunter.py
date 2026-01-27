"""
Unit tests for HeadHunter class (Market Screener & Filtering)

Tests cover:
- Volume filtering (MIN_VOLUME)
- Blacklist rejection
- Whitelist-only mode (TRADING_UNIVERSE = "SAFE_LIST")
- Universe modes (ALL, SAFE_LIST, TOP_30)
- Empty candidates handling
- Database fallback scenarios
"""

import pytest
from src.roles.job_screener import HeadHunter
from unittest.mock import Mock, patch


@pytest.mark.unit
class TestHeadHunterVolumeFiltering:
    """Test volume-based filtering"""
    
    def test_filters_out_low_volume_coins(self, mock_db_with_config):
        """HeadHunter should filter out coins below MIN_VOLUME"""
        # Arrange
        hunter = HeadHunter(mock_db_with_config)
        
        candidates = [
            {'symbol': 'BTC/USDT', 'volume': 100000000},  # Above threshold
            {'symbol': 'ETH/USDT', 'volume': 60000000},   # Above threshold
            {'symbol': 'SHIB/USDT', 'volume': 30000},     # Below threshold (50k)
            {'symbol': 'DOGE/USDT', 'volume': 70000000},  # Above threshold
        ]
        
        # Act
        qualified = hunter.screen_market(candidates)
        
        # Assert
        assert len(qualified) == 3
        symbols = [c['symbol'] for c in qualified]
        assert 'SHIB/USDT' not in symbols
        assert 'BTC/USDT' in symbols
    
    def test_handles_zero_volume(self, mock_db_with_config):
        """HeadHunter should filter out zero volume coins"""
        # Arrange
        hunter = HeadHunter(mock_db_with_config)
        
        candidates = [
            {'symbol': 'BTC/USDT', 'volume': 100000000},
            {'symbol': 'DEAD/USDT', 'volume': 0},  # Zero volume
        ]
        
        # Act
        qualified = hunter.screen_market(candidates)
        
        # Assert
        assert len(qualified) == 1
        assert qualified[0]['symbol'] == 'BTC/USDT'


@pytest.mark.unit
class TestHeadHunterBlacklistWhitelist:
    """Test blacklist/whitelist filtering"""
    
    def test_rejects_blacklisted_coins(self, mock_db):
        """HeadHunter should reject BLACKLIST coins"""
        # Arrange
        hunter = HeadHunter(mock_db)
        hunter.universe = 'ALL'
        hunter.min_volume = 50000
        
        # Mock DB to return fundamental data with blacklist
        def mock_execute():
            return Mock(data=[
                {'symbol': 'BTC/USDT', 'status': 'NEUTRAL'},
                {'symbol': 'SCAM/USDT', 'status': 'BLACKLIST'},
                {'symbol': 'ETH/USDT', 'status': 'WHITELIST'},
            ])
        
        mock_db.table('fundamental_coins').select('*').execute = mock_execute
        
        candidates = [
            {'symbol': 'BTC/USDT', 'volume': 100000000},
            {'symbol': 'SCAM/USDT', 'volume': 80000000},
            {'symbol': 'ETH/USDT', 'volume': 90000000},
        ]
        
        # Act
        qualified = hunter.screen_market(candidates)
        
        # Assert
        assert len(qualified) == 2
        symbols = [c['symbol'] for c in qualified]
        assert 'SCAM/USDT' not in symbols
        assert 'BTC/USDT' in symbols
        assert 'ETH/USDT' in symbols
    
    def test_safe_list_mode_only_allows_whitelist(self, mock_db):
        """HeadHunter in SAFE_LIST mode should only allow WHITELIST coins"""
        # Arrange
        hunter = HeadHunter(mock_db)
        hunter.universe = 'SAFE_LIST'
        hunter.min_volume = 50000
        
        # Mock DB
        def mock_execute():
            return Mock(data=[
                {'symbol': 'BTC/USDT', 'status': 'NEUTRAL'},
                {'symbol': 'ETH/USDT', 'status': 'WHITELIST'},
                {'symbol': 'SOL/USDT', 'status': 'WHITELIST'},
            ])
        
        mock_db.table('fundamental_coins').select('*').execute = mock_execute
        
        candidates = [
            {'symbol': 'BTC/USDT', 'volume': 100000000},  # NEUTRAL - should be rejected
            {'symbol': 'ETH/USDT', 'volume': 90000000},   # WHITELIST - should pass
            {'symbol': 'SOL/USDT', 'volume': 80000000},   # WHITELIST - should pass
        ]
        
        # Act
        qualified = hunter.screen_market(candidates)
        
        # Assert
        assert len(qualified) == 2
        symbols = [c['symbol'] for c in qualified]
        assert 'BTC/USDT' not in symbols  # Rejected (not whitelisted)
        assert 'ETH/USDT' in symbols
        assert 'SOL/USDT' in symbols


@pytest.mark.unit
class TestHeadHunterEdgeCases:
    """Test edge cases and error handling"""
    
    def test_handles_empty_candidates(self, mock_db_with_config):
        """HeadHunter should handle empty candidate list"""
        # Arrange
        hunter = HeadHunter(mock_db_with_config)
        
        # Act
        qualified = hunter.screen_market([])
        
        # Assert
        assert qualified == []
    
    def test_handles_legacy_string_format(self, mock_db_with_config):
        """HeadHunter should handle old format (list of strings instead of dicts)"""
        # Arrange
        hunter = HeadHunter(mock_db_with_config)
        
        # Legacy format (before dict format)
        candidates = ['BTC/USDT', 'ETH/USDT']
        
        # Act - should not crash
        qualified = hunter.screen_market(candidates)
        
        # Assert - All rejected due to volume = 0
        assert len(qualified) == 0
    
    def test_handles_missing_symbol_key(self, mock_db_with_config):
        """HeadHunter should handle candidates with missing 'symbol' key"""
        # Arrange
        hunter = HeadHunter(mock_db_with_config)
        
        candidates = [
            {'volume': 100000000},  # Missing 'symbol'
            {'symbol': 'ETH/USDT', 'volume': 90000000},
        ]
        
        # Act
        qualified = hunter.screen_market(candidates)
        
        # Assert - Only valid candidate should pass
        assert len(qualified) == 1
        assert qualified[0]['symbol'] == 'ETH/USDT'
    
    def test_handles_database_error_gracefully(self, mock_db):
        """HeadHunter should handle DB errors without crashing"""
        # Arrange
        hunter = HeadHunter(mock_db)
        
        # Mock DB to raise exception
        mock_db.table('fundamental_coins').select('*').execute = Mock(side_effect=Exception("DB Connection Failed"))
        
        candidates = [
            {'symbol': 'BTC/USDT', 'volume': 100000000},
            {'symbol': 'ETH/USDT', 'volume': 90000000},
        ]
        
        # Act - should not crash, but fall back to volume-only filtering
        qualified = hunter.screen_market(candidates)
        
        # Assert - Should still work with volume filtering only
        assert len(qualified) == 2


@pytest.mark.unit
class TestHeadHunterConfigReload:
    """Test configuration reloading from DB"""
    
    def test_loads_min_volume_from_config(self, mock_db_with_config):
        """HeadHunter should load MIN_VOLUME from DB config"""
        # Arrange
        hunter = HeadHunter(mock_db_with_config)
        
        # Act
        hunter.load_config()
        
        # Assert
        assert hunter.min_volume == 50000.0
    
    def test_loads_universe_mode_from_config(self, mock_db_with_config):
        """HeadHunter should load TRADING_UNIVERSE from DB config"""
        # Arrange
        hunter = HeadHunter(mock_db_with_config)
        
        # Act
        hunter.load_config()
        
        # Assert
        assert hunter.universe == 'ALL'
    
    def test_uses_defaults_when_db_unavailable(self):
        """HeadHunter should use default values when DB is None"""
        # Arrange
        hunter = HeadHunter(db_client=None)
        
        # Act
        hunter.load_config()
        
        # Assert - Should keep default values
        assert hunter.min_volume == 50000
        assert hunter.universe == 'ALL'
