# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Zenith Trading Bot is an autonomous cryptocurrency trading bot using a multi-agent architecture. It connects to **Binance Thailand** via CCXT, uses **Google Gemini AI** for market analysis, and persists data in **Supabase** (PostgreSQL). Deployed on **Railway** with a Streamlit dashboard.

## Commands

### Python Bot
```bash
python3 main.py                    # Run trading bot
python3 status_server.py           # Run status server
python3 -m pytest                  # Run all tests
python3 -m pytest tests/test_judge.py -v   # Run single test file
python3 -m pytest -m unit          # Run only unit tests
python3 -m pytest -m integration   # Run only integration tests
```

### Frontend (React/Vite)
```bash
npm install        # Install JS dependencies
npm run dev        # Dev server on port 3000
npm run build      # Production build
```

### Dashboard (Streamlit)
```bash
streamlit run dashboard/app.py
```

### Docker
```bash
docker build -t zenith-bot .
docker run --env-file .env zenith-bot   # Runs run.sh → main.py + status_server.py
```

## Architecture

### Two-Phase Trading Cycle

1. **Farming Phase** — Wide market scan (runs every `FARMING_INTERVAL_HOURS`, default 12h). Discovers candidates via Radar → HeadHunter filter → saves `ACTIVE_CANDIDATES` to DB.
2. **Sniping Phase** — Per-pair analysis (runs every `TRADING_CYCLE_MINUTES`, default 2min). For each candidate: PriceSpy → Strategist (AI) → Judge (rules) → Sniper (execute).

### Multi-Agent Pipeline

```
Radar (job_scout.py)         → scans top-volume USDT pairs
HeadHunter (job_screener.py) → filters by volume, blacklist, universe mode
PriceSpy (job_price.py)      → OHLCV data + indicators (RSI, MACD, EMA20/50/200, ATR, BBands, ADX, slopes, price position)
                              → detect_market_trend() for downtrend protection
Strategist (job_analysis.py) → sends tech data + trend context to Gemini AI, gets BUY/SELL/WAIT
Judge (job_analysis.py)      → rule validation + downtrend protection + position sizing
SniperExecutor (job_executor.py) → market order execution (paper or live)
WalletSync (job_wallet.py)   → syncs Binance wallet to DB for dashboard
```

### Key Design Decisions

- **Binance TH workarounds**: CCXT's margin/futures APIs don't work with Binance TH. Raw `privateGetAccount()` and direct HTTP requests to `api.binance.th` are used instead. See `job_wallet.py` and `job_price.py`.
- **Downtrend protection for spot trading**: Since Binance TH doesn't support shorting, the bot uses capital preservation strategy during downtrends. Hybrid detection algorithm (EMA alignment, ADX, price position, momentum) with configurable protection modes. See `docs/DOWNTREND_PROTECTION.md`.
- **Trailing stops check ALL open positions** (not just active candidates) to prevent orphaned positions from being missed.
- **Held positions are auto-injected** into the candidate list even if they dropped off the farm list, so the Strategist can still generate SELL signals.
- **Judge reloads config from DB every evaluate()** call so dashboard changes take effect immediately.
- **WAIT/HOLD signals are skipped entirely** — no DB write, no Judge evaluation.
- **Position close records exit_price and pnl** on the `positions` table (columns: `exit_price FLOAT`, `pnl FLOAT`).
- **Live order fill_price has fallback**: Binance market orders often return `price: null`. The Sniper falls back to `order['average']`, then to `fetch_ticker()` as last resort. Never stores `entry_avg: 0`.
- **Duplicate BUY rejected**: Judge checks if an open position already exists for the same asset before approving a BUY.
- **SELL rejected if no position**: Judge rejects SELL signals when no open position exists, preventing wasted Sniper execution.
- **NewsSpy is a placeholder** (`job_news.py`): Not used in the pipeline. Removed from `main.py` imports.
- **Status server pings Binance** (`/api/v1/ping`) to verify real connectivity, not just env var presence.

### Configuration

All config lives in the `bot_config` Supabase table as key-value pairs. Key settings: `TRADING_MODE` (PAPER/LIVE), `RSI_THRESHOLD`, `AI_CONF_THRESHOLD`, `POSITION_SIZE_PCT`, `MAX_OPEN_POSITIONS`, `TRAILING_STOP_ENABLED`, `TRAILING_STOP_USE_ATR`, `TRAILING_STOP_PCT`, `TRAILING_STOP_ATR_MULTIPLIER`, `MIN_PROFIT_TO_TRAIL_PCT`, `ENABLE_DOWNTREND_PROTECTION`, `DOWNTREND_PROTECTION_MODE`, `DOWNTREND_AI_BOOST`, `DOWNTREND_SIZE_REDUCTION_PCT`, `ADX_TREND_THRESHOLD`.

### Database Tables

Core tables: `bot_config`, `assets`, `positions`, `trade_signals`, `simulation_portfolio`, `wallet_balance`, `system_logs`, `farming_history`, `fundamental_coins`, `audit_log`.

### Entry Points

- `main.py` — Bot orchestrator (runs on Railway as background worker)
- `status_server.py` — HTTP health check endpoint (Railway web process)
- `dashboard/app.py` — Streamlit monitoring dashboard
- `run.sh` — Docker entrypoint that starts both main.py and status_server.py

## Environment Variables

Required: `SUPABASE_URL`, `SUPABASE_KEY`, `GEMINI_API_KEY`, `BINANCE_API_KEY`, `BINANCE_SECRET`, `BINANCE_API_URL` (https://api.binance.th for TH). See `.env.example`.

## Completed Features

### 2025-01-29
- **Downtrend Protection System**: Hybrid multi-indicator trend detection (EMA 200, ADX, price position, slope, DM) with 3 protection modes (STRICT/MODERATE/SELECTIVE). Capital preservation strategy for spot-only trading. See `docs/DOWNTREND_PROTECTION.md`

### 2025-01-28
- **P&L Display**: Implemented in history_page, dashboard_page, wallet_page, status_server
- **ATR Trailing Stop UI**: Added USE_ATR toggle and ATR_MULTIPLIER input to config_page
- **Simulation Page Fixes**: Fixed PnL % calculation, cached ticker fetches, added closed trades table
- **Fundamental Lab Enhancement**: CoinGecko auto-fetch, auto-scoring, auto-classification, P&L correlation
- **AI Performance Report**: Enhanced `Strategist.generate_performance_report()` with structured data

---

## Planned Features / TODO

### 1. Trading Sessions & Comprehensive Performance Tracking
**Status**: ✅ IMPLEMENTED (2025-01-28)
**Problem**: Cannot track performance from fresh start; no session-based win/loss tracking.

**New Database Tables Required**:

```sql
-- trading_sessions: Track each simulation/live trading "run"
CREATE TABLE trading_sessions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_name TEXT,                    -- "Paper Run #3" or "Live Week 1"
    mode TEXT NOT NULL,                   -- 'PAPER' or 'LIVE'
    start_balance NUMERIC NOT NULL,
    current_balance NUMERIC NOT NULL,
    started_at TIMESTAMPTZ DEFAULT NOW(),
    ended_at TIMESTAMPTZ,                 -- NULL if active
    is_active BOOLEAN DEFAULT TRUE,

    -- Aggregate Performance (updated after each trade close)
    total_trades INT DEFAULT 0,
    winning_trades INT DEFAULT 0,
    losing_trades INT DEFAULT 0,
    gross_profit NUMERIC DEFAULT 0,       -- Sum of all wins
    gross_loss NUMERIC DEFAULT 0,         -- Sum of all losses (positive number)
    net_pnl NUMERIC DEFAULT 0,            -- gross_profit - gross_loss

    -- Advanced Metrics
    largest_win NUMERIC DEFAULT 0,
    largest_loss NUMERIC DEFAULT 0,
    avg_win NUMERIC DEFAULT 0,
    avg_loss NUMERIC DEFAULT 0,
    win_rate NUMERIC DEFAULT 0,
    profit_factor NUMERIC DEFAULT 0,      -- gross_profit / gross_loss
    max_drawdown NUMERIC DEFAULT 0,
    max_drawdown_pct NUMERIC DEFAULT 0,

    -- Config Snapshot (JSON of bot_config at session start)
    config_snapshot JSONB,

    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- config_change_log: Track parameter changes during session
CREATE TABLE config_change_log (
    id BIGSERIAL PRIMARY KEY,
    session_id UUID REFERENCES trading_sessions(id),
    key TEXT NOT NULL,
    old_value TEXT,
    new_value TEXT,
    changed_at TIMESTAMPTZ DEFAULT NOW()
);

-- balance_snapshots: For drawdown calculation
CREATE TABLE balance_snapshots (
    id BIGSERIAL PRIMARY KEY,
    session_id UUID REFERENCES trading_sessions(id),
    balance NUMERIC NOT NULL,
    equity NUMERIC NOT NULL,              -- balance + unrealized PnL
    peak_equity NUMERIC NOT NULL,
    drawdown NUMERIC DEFAULT 0,
    drawdown_pct NUMERIC DEFAULT 0,
    snapshot_at TIMESTAMPTZ DEFAULT NOW()
);

-- Add session reference to positions
ALTER TABLE positions ADD COLUMN session_id UUID REFERENCES trading_sessions(id);
```

**Implementation Points**:
- After each trade closes, call `update_session_stats(session_id, trade_pnl)` to update aggregates
- Calculate: `win_rate`, `profit_factor`, `avg_win`, `avg_loss` on each update
- Take balance snapshots every trading cycle for drawdown tracking
- Link each position to its session via `session_id`

---

### 2. Paper Mode Reset & Historical Tracking
**Status**: ✅ IMPLEMENTED (2025-01-28)
**Problem**: No way to reset paper trading; no historical simulation runs preserved.

**UI Requirements** (in config_page.py):
```
┌─────────────────────────────────────────────┐
│ 🔄 Paper Trading Session                    │
│                                             │
│ Current: "Paper Run #2"                     │
│ Started: 2025-01-20 | Balance: $1,234.56   │
│                                             │
│ [🆕 Start New Simulation]                   │
│   Starting Balance: [____1000____]          │
│   Session Name: [__Paper Run #3__]          │
│                                             │
│   [🔄 Reset & Start Fresh]                  │
└─────────────────────────────────────────────┘
```

**Reset Flow**:
1. End current session (`ended_at = NOW()`, `is_active = false`)
2. Snapshot final stats to `trading_sessions` table
3. Create NEW session with user-specified `start_balance`
4. Snapshot current `bot_config` to `config_snapshot` JSONB
5. Reset `simulation_portfolio.balance` to new start balance
6. Keep all positions/signals (linked to old `session_id`)

**New Page**: `session_history_page.py` — View all past simulation runs with their configs and results.

---

### 3. Capital Protection / Profit Transfer System
**Status**: ✅ IMPLEMENTED (2025-01-28)
**Problem**: No way to protect profits; bot uses entire wallet balance.

**Concept: Virtual Wallet Separation**
```
┌───────────────────────────────────────────────┐
│         USER'S BINANCE ACCOUNT                │
│                                               │
│   ┌─────────────────┐  ┌─────────────────┐   │
│   │  Profit Reserve │  │ Trading Capital │   │
│   │  (Protected)    │  │ (Bot uses this) │   │
│   │  $500.00        │  │ $1,000.00       │   │
│   └─────────────────┘  └─────────────────┘   │
│            ▲                    │             │
│            │   Auto-transfer    │             │
│            └────────────────────┘             │
│         (50% of profits moved)               │
└───────────────────────────────────────────────┘
```

**Database Table**:
```sql
CREATE TABLE capital_allocation (
    id SERIAL PRIMARY KEY,
    mode TEXT NOT NULL,                    -- 'PAPER' or 'LIVE'

    -- User-defined limits
    trading_capital NUMERIC NOT NULL,      -- Max amount bot can use
    profit_reserve NUMERIC DEFAULT 0,      -- Accumulated profits (protected)

    -- Auto-transfer settings
    auto_transfer_enabled BOOLEAN DEFAULT FALSE,
    transfer_threshold NUMERIC DEFAULT 100, -- Min profit to trigger transfer
    transfer_percentage NUMERIC DEFAULT 50, -- % of profit to transfer

    -- Tracking
    total_deposited NUMERIC DEFAULT 0,
    total_withdrawn NUMERIC DEFAULT 0,

    updated_at TIMESTAMPTZ DEFAULT NOW()
);
```

**Bot Logic Changes**:
```python
def get_available_trading_balance():
    """Bot only sees trading_capital, not profit_reserve"""
    allocation = get_capital_allocation()
    actual_balance = get_binance_usdt_balance()
    return min(actual_balance, allocation.trading_capital)

def after_trade_close(pnl):
    if pnl > 0 and allocation.auto_transfer_enabled:
        if pnl >= allocation.transfer_threshold:
            transfer = pnl * (allocation.transfer_percentage / 100)
            allocation.profit_reserve += transfer
            allocation.trading_capital -= transfer  # Reduce available capital
```

**UI Requirements** (new `capital_page.py`):
- Show Trading Capital vs Profit Reserve split
- Enable/disable auto-transfer
- Set threshold and percentage
- Manual transfer buttons (Trading ↔ Reserve)
- Works for both PAPER and LIVE modes

**Note**: This is VIRTUAL separation (database tracking only). No actual Binance sub-account transfers needed. Bot simply respects `trading_capital` limit.

---

### 4. Exit Reason Tracking & Analytics
**Status**: NOT IMPLEMENTED
**Problem**: No visibility into WHY positions were closed; can't analyze which exit strategies work best.

**Value**: Enable users and AI to analyze exit effectiveness, optimize configurations, and identify patterns in trading behavior.

**Database Changes**:
```sql
-- Add exit_reason column to positions table
ALTER TABLE positions ADD COLUMN exit_reason TEXT;

-- Create index for analysis queries
CREATE INDEX idx_positions_exit_reason ON positions(exit_reason);
```

**Exit Reason Categories**:
- `AI_SELL_SIGNAL` - Strategist AI recommended SELL
- `TRAILING_STOP` - Trailing stop triggered (price dropped X% from peak)
- `STOP_LOSS` - Hard stop loss hit (if implemented)
- `TAKE_PROFIT` - Take profit target reached (if implemented)
- `MANUAL_CLOSE` - User/dashboard manually closed position
- `MAX_HOLD_TIME` - Position exceeded max hold duration (if implemented)
- `EMERGENCY_CLOSE` - Bot emergency stop triggered
- `SESSION_END` - Position closed when session ended/reset

**Implementation Points**:
1. **job_executor.py**: Add `exit_reason` parameter when closing positions
   ```python
   def close_position(pos_id, exit_price, pnl, exit_reason):
       db.table("positions").update({
           "is_open": False,
           "exit_price": exit_price,
           "pnl": pnl,
           "exit_reason": exit_reason,
           "closed_at": datetime.utcnow().isoformat()
       }).eq("id", pos_id).execute()
   ```

2. **main.py**: Pass `"TRAILING_STOP"` when trailing stop triggers (line ~296)
   ```python
   success = sniper.execute_order(full_signal, exit_reason="TRAILING_STOP")
   ```

3. **Judge**: Could add stop-loss/take-profit logic and pass appropriate reasons

4. **history_page.py**: Add `exit_reason` column to closed positions table
   - Color-code by reason type (green for AI_SELL, orange for TRAILING_STOP, etc.)

5. **session_history_page.py**: Show exit reason breakdown per session
   - Bar chart: % of exits by type
   - Win rate by exit reason

6. **Strategist.generate_performance_report()**: Feed exit reason statistics to AI
   ```python
   exit_breakdown = {
       'AI_SELL_SIGNAL': {'count': 10, 'avg_pnl': 50.25, 'win_rate': 80},
       'TRAILING_STOP': {'count': 5, 'avg_pnl': 30.10, 'win_rate': 100}
   }
   ```

**Analytics Insights**:
- **Win rate by exit type**: Do AI SELLs outperform trailing stops?
- **Average P&L by exit reason**: Which method captures most profit?
- **Timing analysis**: Are trailing stops exiting too early/late?
- **Strategy optimization**: Adjust configs based on exit performance
- **Pattern detection**: Do certain coins perform better with specific exit types?
- **AI feedback loop**: Feed exit data back to Strategist for improved SELL timing

**Dashboard Enhancements**:
- Add filter in Trade History: "Show only Trailing Stop exits"
- Add metric card: "Most Profitable Exit Method"
- Add chart: "Exit Method Distribution" (pie chart)
- Add comparison table: Win rate vs Avg P&L by exit reason

**Example AI Analysis Output**:
```
Exit Strategy Performance:
- AI SELL Signals: 75% win rate, $45 avg profit
- Trailing Stops: 100% win rate, $28 avg profit
- Recommendation: Trailing stops preserve capital but exit early.
  Consider tightening AI SELL criteria or widening trailing stop %.
```

---

## Documentation

- `docs/FUNCTIONAL_DOCUMENT.md` — Full function-level documentation of every module and calculation
- `docs/DOWNTREND_PROTECTION.md` — Downtrend protection system design and implementation
- `docs/PAPER_MONITORING_PHASE.md` — 7-day paper testing guide with tracking templates
- `docs/ATR_TRAILING_STOP_CONFIG.md` — Trailing stop configuration guide
- `docs/SECURITY.md` — Security practices and secret management
- `docs/AUTHENTICATION_SETUP.md` — Dashboard auth setup
