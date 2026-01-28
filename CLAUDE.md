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
PriceSpy (job_price.py)      → OHLCV data + indicators (RSI, MACD, EMA, ATR, BBands)
Strategist (job_analysis.py) → sends tech data to Gemini AI, gets BUY/SELL/WAIT
Judge (job_analysis.py)      → rule validation + position sizing
SniperExecutor (job_executor.py) → market order execution (paper or live)
WalletSync (job_wallet.py)   → syncs Binance wallet to DB for dashboard
```

### Key Design Decisions

- **Binance TH workarounds**: CCXT's margin/futures APIs don't work with Binance TH. Raw `privateGetAccount()` and direct HTTP requests to `api.binance.th` are used instead. See `job_wallet.py` and `job_price.py`.
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

All config lives in the `bot_config` Supabase table as key-value pairs. Key settings: `TRADING_MODE` (PAPER/LIVE), `RSI_THRESHOLD`, `AI_CONF_THRESHOLD`, `POSITION_SIZE_PCT`, `MAX_OPEN_POSITIONS`, `TRAILING_STOP_ENABLED`, `TRAILING_STOP_USE_ATR`, `TRAILING_STOP_PCT`, `TRAILING_STOP_ATR_MULTIPLIER`, `MIN_PROFIT_TO_TRAIL_PCT`.

### Database Tables

Core tables: `bot_config`, `assets`, `positions`, `trade_signals`, `simulation_portfolio`, `wallet_balance`, `system_logs`, `farming_history`, `fundamental_coins`, `audit_log`.

### Entry Points

- `main.py` — Bot orchestrator (runs on Railway as background worker)
- `status_server.py` — HTTP health check endpoint (Railway web process)
- `dashboard/app.py` — Streamlit monitoring dashboard
- `run.sh` — Docker entrypoint that starts both main.py and status_server.py

## Environment Variables

Required: `SUPABASE_URL`, `SUPABASE_KEY`, `GEMINI_API_KEY`, `BINANCE_API_KEY`, `BINANCE_SECRET`, `BINANCE_API_URL` (https://api.binance.th for TH). See `.env.example`.

## Planned Features / TODO

### P&L Display & Performance Analytics
**Status**: Data is stored (`positions.exit_price`, `positions.pnl`) but not surfaced in UI.
**Where to implement**:
1. `dashboard/ui/history_page.py` — Primary: table of closed positions showing symbol, entry_avg, exit_price, quantity, pnl, return %. This is the main trade history view.
2. `dashboard/ui/dashboard_page.py` — Summary card: total realized P&L, win rate, best/worst trade.
3. `dashboard/ui/wallet_page.py` — Cumulative realized P&L alongside wallet balance.
4. `status_server.py` — Simple line: total PnL + win rate for Railway quick-check.
5. `Strategist.generate_performance_report()` — Feed closed positions with pnl data for AI performance review (function exists but lacks real data).

### AI Performance Analysis Report (Post-Core)
**Status**: `Strategist.generate_performance_report()` exists but uses a generic prompt with no structured data. Build after all core functions are stable.
**Data to feed AI**:
1. Closed positions: entry_avg, exit_price, pnl, return %, hold duration, symbol.
2. Trade signals: total count, approved/rejected ratio, rejection reasons breakdown.
3. Judge guardrail stats: how often RSI veto, EMA veto, MACD veto, confidence reject, position limit triggered.
4. Farming history: candidates per cycle, recurring symbols.
5. Win rate by symbol and by time window.
6. Config change impact: before/after comparison when settings change.
7. Trailing stop vs AI SELL: which exit method captured more profit.
**AI output should include**: P&L summary, best/worst coins, config recommendations, pattern observations, blacklist suggestions.

### Simulation Page Fixes (`dashboard/ui/simulation_page.py`)
**Issues found**:
1. Unrealized PnL % is hardcoded `(unrealized_pnl/1000)*100` — should divide by actual `balance`, not 1000.
2. Fetches tickers twice per open position (line 23 in summary loop, line 43 in card loop). Should fetch once and reuse.
3. History table shows signals but not exit_price or pnl from closed positions.

### Missing ATR Trailing Stop UI in Config Page (`dashboard/ui/config_page.py`)
**Status**: Config page has basic trailing stop settings (enable, trail %, min profit %) but is missing:
1. `TRAILING_STOP_USE_ATR` — Toggle to switch between fixed % and ATR-based mode.
2. `TRAILING_STOP_ATR_MULTIPLIER` — ATR multiplier input (default 2.0).
These keys exist in bot_config and are used by `main.py:203-212` but have no dashboard UI.

### Fundamental Lab Enhancement
**Status**: Currently a manual CRUD page (`dashboard/ui/fundamental_page.py`) for the `fundamental_coins` table. HeadHunter only uses the `status` field (WHITELIST/BLACKLIST/NEUTRAL) — the `manual_score` field has no effect on the pipeline.
**What's missing**:
1. Auto-fetch fundamentals from CoinGecko/CoinMarketCap API (market cap, supply, volume trends).
2. Auto-scoring engine to calculate a fundamental score from fetched data.
3. Auto-classify coins: high score → WHITELIST, low score → BLACKLIST.
4. Make `manual_score` (or auto-score) influence HeadHunter filtering or Judge confidence.
5. Correlate fundamental scores with actual P&L performance (once P&L display is built).

---

## Documentation

- `docs/FUNCTIONAL_DOCUMENT.md` — Full function-level documentation of every module and calculation
- `docs/ATR_TRAILING_STOP_CONFIG.md` — Trailing stop configuration guide
- `docs/SECURITY.md` — Security practices and secret management
- `docs/AUTHENTICATION_SETUP.md` — Dashboard auth setup
