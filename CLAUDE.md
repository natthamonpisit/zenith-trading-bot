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

## Documentation

- `docs/FUNCTIONAL_DOCUMENT.md` — Full function-level documentation of every module and calculation
- `docs/ATR_TRAILING_STOP_CONFIG.md` — Trailing stop configuration guide
- `docs/SECURITY.md` — Security practices and secret management
- `docs/AUTHENTICATION_SETUP.md` — Dashboard auth setup
