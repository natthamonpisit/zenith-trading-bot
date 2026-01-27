"""
Audit logging for sensitive operations.

Logs critical events to database for security review.
"""

import logging
from datetime import datetime
from typing import Optional
from src.database import get_db


class AuditLogger:
    """
    Log sensitive operations to database for security audit.
    
    Logs events like:
    - Order executions
    - Config changes
    - Balance modifications
    
    Example:
        audit = AuditLogger()
        audit.log_order("BTC/USDT", "BUY", 0.1, is_sim=False)
        audit.log_config_change("TRADING_MODE", "PAPER", "LIVE")
    """
    
    def __init__(self):
        self.db = get_db()
        self.logger = logging.getLogger("audit")
        
        # Configure logger
        if not self.logger.handlers:
            handler = logging.StreamHandler()
            formatter = logging.Formatter(
                '[%(asctime)s] AUDIT: %(message)s',
                datefmt='%Y-%m-%d %H:%M:%S'
            )
            handler.setFormatter(formatter)
            self.logger.addHandler(handler)
            self.logger.setLevel(logging.INFO)
    
    def log_order(self, symbol: str, side: str, amount: float, is_sim: bool, price: Optional[float] = None):
        """
        Log order execution.
        
        Args:
            symbol: Trading pair (e.g. 'BTC/USDT')
            side: 'BUY' or 'SELL'
            amount: Order amount
            is_sim: Is simulation order
            price: Execution price (optional)
        """
        entry = {
            "event_type": "ORDER_EXECUTED",
            "symbol": symbol,
            "side": side,
            "amount": float(amount),
            "is_sim": is_sim,
            "price": float(price) if price else None,
            "timestamp": datetime.utcnow().isoformat()
        }
        self._write_audit(entry)
        self.logger.info(f"ORDER {side} {amount} {symbol} @ ${price or 'market'} (sim={is_sim})")
    
    def log_config_change(self, key: str, old_value, new_value, user: str = "system"):
        """
        Log configuration modification.
        
        Args:
            key: Config key name
            old_value: Previous value
            new_value: New value
            user: Who made the change
        """
        entry = {
            "event_type": "CONFIG_CHANGED",
            "key": key,
            "old_value": str(old_value),
            "new_value": str(new_value),
            "user": user,
            "timestamp": datetime.utcnow().isoformat()
        }
        self._write_audit(entry)
        self.logger.info(f"CONFIG {key}: {old_value} → {new_value} (by {user})")
    
    def log_balance_change(self, amount: float, balance_before: float, balance_after: float, reason: str, is_sim: bool = True):
        """
        Log balance modification.
        
        Args:
            amount: Change amount (+ or -)
            balance_before: Balance before change
            balance_after: Balance after change
            reason: Reason for change
            is_sim: Is simulation balance
        """
        entry = {
            "event_type": "BALANCE_CHANGED",
            "amount": float(amount),
            "balance_before": float(balance_before),
            "balance_after": float(balance_after),
            "reason": reason,
            "is_sim": is_sim,
            "timestamp": datetime.utcnow().isoformat()
        }
        self._write_audit(entry)
        self.logger.info(f"BALANCE {'+' if amount >= 0 else ''}{amount} (${balance_before} → ${balance_after}): {reason}")
    
    def log_signal_created(self, symbol: str, signal_type: str, status: str, reason: str):
        """
        Log signal creation.
        
        Args:
            symbol: Trading pair
            signal_type: 'BUY', 'SELL', 'WAIT'
            status: 'PENDING', 'APPROVED', 'REJECTED'
            reason: Judge decision reason
        """
        entry = {
            "event_type": "SIGNAL_CREATED",
            "symbol": symbol,
            "signal_type": signal_type,
            "status": status,
            "reason": reason[:200],  # Truncate long reasons
            "timestamp": datetime.utcnow().isoformat()
        }
        self._write_audit(entry)
        self.logger.info(f"SIGNAL {signal_type} {symbol} → {status}")
    
    def _write_audit(self, entry: dict):
        """
        Write audit entry to database.
        
        Args:
            entry: Audit event data
        """
        try:
            if self.db:
                self.db.table("audit_log").insert(entry).execute()
        except Exception as e:
            # Never fail the main operation due to audit logging
            self.logger.error(f"Failed to write audit log: {e}")


# Global instance
_audit_logger = None

def get_audit_logger() -> AuditLogger:
    """Get global audit logger instance"""
    global _audit_logger
    if _audit_logger is None:
        _audit_logger = AuditLogger()
    return _audit_logger
