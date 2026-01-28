# Zenith Trading Bot - Functional Document

## Table of Contents

1. [System Overview](#1-system-overview)
2. [Architecture](#2-architecture)
3. [Main Orchestrator (main.py)](#3-main-orchestrator)
4. [Data Models (src/models/)](#4-data-models)
5. [Agent Roles (src/roles/)](#5-agent-roles)
6. [Utility Modules (src/utils/)](#6-utility-modules)
7. [Database Layer (src/database.py)](#7-database-layer)
8. [Calculation Reference](#8-calculation-reference)
9. [Configuration Keys](#9-configuration-keys)
10. [Trading Flow Summary](#10-trading-flow-summary)

---

## 1. System Overview

**Zenith AI Bot** is an autonomous cryptocurrency trading bot using a multi-agent architecture. It runs on Railway (cloud), connects to **Binance Thailand** (or Binance Global) via CCXT, uses **Google Gemini AI** for market analysis, and persists all data in **Supabase** (PostgreSQL).

**Key capabilities:**
- Automated market scanning (farming) and trade execution (sniping)
- AI-powered technical analysis via Google Gemini
- Rule-based trade validation (Judge)
- Trailing stop-loss with ATR-based or fixed-percentage modes
- Paper trading (simulation) and live trading modes
- Streamlit dashboard for monitoring and configuration
- Watchdog process for crash recovery

---

## 2. Architecture

### 2.1 Multi-Agent Roles

| Role | Class | File | Purpose |
|------|-------|------|---------|
| Radar | `Radar` | `job_scout.py` | Scans market for top-volume trading candidates |
| HeadHunter | `HeadHunter` | `job_screener.py` | Filters candidates by fundamentals (volume, whitelist/blacklist) |
| PriceSpy | `PriceSpy` | `job_price.py` | Fetches OHLCV data and calculates technical indicators |
| NewsSpy | `NewsSpy` | `job_news.py` | News sentiment analysis (placeholder) |
| Strategist | `Strategist` | `job_analysis.py` | AI-powered market analysis using Google Gemini |
| Judge | `Judge` | `job_analysis.py` | Rule-based trade validation and position sizing |
| Sniper | `SniperExecutor` | `job_executor.py` | Executes buy/sell orders (paper or live) |
| WalletSync | `WalletSync` | `job_wallet.py` | Syncs Binance wallet balance to database |

### 2.2 Data Flow

```
Radar.scan_market()          -- fetches top USDT pairs by 24h volume
       |
       v
HeadHunter.screen_market()   -- filters by volume, blacklist, universe mode
       |
       v
PriceSpy.fetch_ohlcv()       -- fetches OHLCV candle data
PriceSpy.calculate_indicators() -- RSI, MACD, EMA, ATR, Bollinger Bands
       |
       v
Strategist.analyze_market()  -- sends tech data to Gemini AI, gets recommendation
       |
       v
Judge.evaluate()             -- validates against rules, calculates position size
       |
       v
SniperExecutor.execute_order() -- places market order (paper or live)
```

### 2.3 Two-Phase Cycle

1. **Farming Phase** - Wide market scan to discover candidates. Runs every N hours (configurable via `FARMING_INTERVAL_HOURS`).
2. **Sniping Phase** - Processes each candidate through the full pipeline. Runs every N minutes (configurable via `TRADING_CYCLE_MINUTES`, default 2).

---

## 3. Main Orchestrator (main.py)

### 3.1 `start()`
**Entry point of the bot.**

1. Logs startup to `system_logs` table.
2. Starts watchdog thread (crash recovery).
3. Writes initial heartbeat to DB so dashboard shows bot is alive.
4. Reads `TRADING_MODE` from DB (PAPER or LIVE).
5. Runs `wallet_sync.sync_wallet()` immediately.
6. Runs first `run_trading_cycle()`.
7. Schedules `run_trading_cycle()` every `TRADING_CYCLE_MINUTES` (default 2 min).
8. Schedules `wallet_sync.sync_wallet()` every 5 minutes.
9. Enters infinite loop running `schedule.run_pending()` every 1 second.

### 3.2 `run_trading_cycle()`
**Main trading loop, runs every cycle.**

1. Updates heartbeat.
2. Checks if bot is stopped (`BOT_STATUS == "STOPPED"`).
3. Calls `check_trailing_stops()` for all open positions.
4. Checks if farming is needed:
   - Reads `LAST_FARM_TIME` and `ACTIVE_CANDIDATES` from DB.
   - Reads `FARMING_INTERVAL_HOURS` (default 12h).
   - If no candidates exist or time elapsed > interval, runs `run_farming_cycle()`.
5. Loads candidate list from DB.
6. Reads `TIMEFRAME` config (default "1h").
7. Iterates each candidate symbol, calling `process_pair(symbol, timeframe)`.

### 3.3 `run_farming_cycle()`
**Discovers new trading candidates.**

1. Logs farming start to `farming_history` table.
2. Calls `radar.scan_market()` - returns top-volume USDT pairs.
3. Calls `head_hunter.screen_market(candidates_raw)` - filters by volume/blacklist.
4. Saves qualified symbol list to `bot_config` as `ACTIVE_CANDIDATES` (JSON array).
5. Updates `LAST_FARM_TIME` timestamp.
6. Updates `farming_history` record with completion status.

### 3.4 `process_pair(pair, timeframe)`
**Full analysis + execution pipeline for one trading pair.**

1. **PriceSpy**: Fetches OHLCV data and calculates indicators.
2. **Strategist**: Sends last 5 rows of technical data to Gemini AI. Receives `{sentiment_score, confidence, reasoning, recommendation}`.
3. **Judge**: Evaluates AI recommendation against hard rules. Returns `APPROVED` or `REJECTED` with position size.
4. **Sniper**: If approved, executes the order. Records signal and position in DB.

### 3.5 `check_trailing_stops()`
**Monitors all open positions for trailing stop triggers.**

1. Reads config: `TRAILING_STOP_ENABLED`, `TRAILING_STOP_USE_ATR`, `TRAILING_STOP_PCT`, `TRAILING_STOP_ATR_MULTIPLIER`, `MIN_PROFIT_TO_TRAIL_PCT`.
2. Fetches all open positions from `positions` table.
3. For each position:
   - Fetches current price via `fetch_ticker()`.
   - Updates `highest_price_seen` if current price > previous peak.
   - Checks if minimum profit threshold is reached: `(highest - entry) / entry >= min_profit_pct`.
   - Calculates trailing stop price (see [Section 8.5](#85-trailing-stop-calculation)).
   - If `current_price <= trail_price`: creates a SELL signal and executes it.

### 3.6 `is_bot_stopped()`
Reads `BOT_STATUS` from `bot_config` table. Returns `True` if value equals `"STOPPED"`.

### 3.7 `log_activity(role, message, level)`
Prints to console and inserts into `system_logs` table with role, message, and level.

### 3.8 `start_watchdog()`
**Background thread for crash detection.**

- Runs every 60 seconds.
- If no heartbeat for 300 seconds (5 min), forces process exit via `os._exit(1)`.
- Writes heartbeat timestamp to `bot_config` table for dashboard visibility.

### 3.9 `get_heartbeat()` / `set_heartbeat()`
Thread-safe heartbeat tracking using `threading.Lock`. Stores `time.time()` value.

### 3.10 `update_status_db(msg)`
Upserts `BOT_STATUS_DETAIL` key in `bot_config` with the given status message.

---

## 4. Data Models (src/models/)

### 4.1 `BotConfig` (config.py)
Pydantic model for validating bot configuration key-value pairs.

| Field | Type | Validation |
|-------|------|------------|
| `key` | str | 1-100 chars, alphanumeric + underscores/hyphens, auto-uppercased |
| `value` | str | Non-empty, trimmed |

### 4.2 `TradeSignal` (signal.py)
Validates signal data before DB insertion.

| Field | Type | Validation |
|-------|------|------------|
| `asset_id` | int | > 0 |
| `signal_type` | Literal | "BUY", "SELL", or "WAIT" |
| `entry_target` | float | > 0, <= 10,000,000 |
| `entry_atr` | float | >= 0 (default 0.0) |
| `status` | Literal | "PENDING", "EXECUTED", or "REJECTED" |
| `judge_reason` | str | 5-500 chars |
| `is_sim` | bool | Required |

### 4.3 `TradeDecision` (decision.py)
Judge's output model.

| Field | Type | Validation |
|-------|------|------------|
| `decision` | str | "APPROVED" or "REJECTED" |
| `size` | float | >= 0 (USDT amount) |
| `reason` | str | 5-500 chars |

### 4.4 `Position` (position.py)
Tracks open/closed positions.

| Field | Type | Validation |
|-------|------|------------|
| `asset_id` | int | > 0 |
| `side` | Literal | "LONG" or "SHORT" |
| `entry_avg` | float | > 0, <= 10M |
| `quantity` | float | > 0, <= 1M |
| `is_open` | bool | Required |
| `is_sim` | bool | Required |
| `entry_atr` | float | >= 0 |
| `highest_price_seen` | float | > 0 |
| `trailing_stop_price` | float | Optional, > 0 if set |

---

## 5. Agent Roles (src/roles/)

### 5.1 HeadHunter (job_screener.py)

**Purpose**: Filters raw market candidates by fundamental/config rules.

#### `__init__(self, db_client)`
- Stores DB reference.
- Sets defaults: `min_volume = 50000` USDT, `universe = "ALL"`.

#### `load_config(self)`
- Reads entire `bot_config` table.
- Updates `min_volume` from `MIN_VOLUME` key.
- Updates `universe` from `TRADING_UNIVERSE` key (values: `ALL`, `SAFE_LIST`, `TOP_30`).

#### `screen_market(self, candidates) -> list`
- Reloads config from DB.
- Fetches `fundamental_coins` table for whitelist/blacklist status.
- For each candidate:
  - **Blacklist check**: Skips if `status == 'BLACKLIST'`.
  - **Volume check**: Skips if `volume < min_volume`.
  - **Universe check**: If `universe == "SAFE_LIST"`, skips non-whitelisted coins.
- Returns list of qualified candidates.

---

### 5.2 PriceSpy (job_price.py)

**Purpose**: Fetches market data from Binance and calculates technical indicators.

#### `__init__(self, exchange_id='binance')`
- Reads `BINANCE_API_KEY`, `BINANCE_SECRET`, `BINANCE_API_URL` from environment.
- Initializes circuit breaker (`failure_threshold=5`, `timeout=60s`).
- Initializes ticker cache (`ttl=5s`, `max_size=500`).
- Initializes rate limiter (`1000 calls / 60s`).
- For **Binance TH**: Overrides API URLs to v1 endpoints, disables margin/futures/swap features.
- For **other exchanges**: Standard CCXT initialization.

#### `fetch_ohlcv(self, symbol, timeframe='1h', limit=100) -> DataFrame`
- Lazy-loads markets if not loaded.
- Calls `exchange.fetch_ohlcv()`.
- Returns DataFrame with columns: `timestamp, open, high, low, close, volume`.

#### `calculate_indicators(self, df) -> DataFrame`
Calculates technical indicators using pandas-ta:

| Indicator | Function | Parameters | Output Column(s) |
|-----------|----------|------------|-------------------|
| RSI | `df.ta.rsi()` | length=14 | `rsi` |
| EMA 20 | `df.ta.ema()` | length=20 | `ema_20` |
| EMA 50 | `df.ta.ema()` | length=50 | `ema_50` |
| MACD | `df.ta.macd()` | fast=12, slow=26, signal=9 | `macd`, `signal` |
| ATR | `df.ta.atr()` | length=14 | `atr` |
| Bollinger Bands | `df.ta.bbands()` | length=20, std=2 | `bb_upper`, `bb_lower`, `sma_20` |

After calculation, NaN values are filled using backfill then forward-fill.

#### `get_top_symbols(self, limit=30, callback, logger) -> list[dict]`
- Loads all USDT pairs from exchange.
- If `limit < 20`: Uses hardcoded safe list (BTC, ETH, SOL, BNB, XRP, DOGE, ADA, LINK, DOT, POL).
- If `limit >= 20`: Scans all available USDT pairs.
- **Binance TH**: Fetches tickers individually (no batch endpoint), sleeps 0.15s between requests.
- **Other exchanges**: Uses batch `fetch_tickers()` with fallback to individual requests.
- Calculates volume as `quoteVolume` or `baseVolume * lastPrice`.
- Sorts by volume descending.
- Fallback: Returns `[BTC/USDT, ETH/USDT]` if all else fails.

#### `get_usdt_thb_rate(self) -> float`
Fetches USDT/THB ticker price. Fallback: returns `35.0`.

#### `get_account_balance(self) -> dict`
Fetches spot account balance via `exchange.fetch_balance({'type': 'spot'})`.

#### `load_markets_custom(self)`
- **Binance TH**: Fetches `exchangeInfo` from `api.binance.th/api/v1`, parses active TRADING symbols, calls `exchange.set_markets()`.
- **Other**: Standard `exchange.load_markets()`.

#### `_fetch_ticker_protected(self, symbol) -> dict`
Fetches single ticker with cache (5s TTL) and circuit breaker protection.

#### `_fetch_tickers_protected(self) -> dict`
Fetches all tickers with cache (5s TTL) and circuit breaker protection.

---

### 5.3 NewsSpy (job_news.py)

**Purpose**: News sentiment analysis.

**Status**: Placeholder. `fetch_latest_news()` returns empty list `[]`.

---

### 5.4 Radar (job_scout.py)

**Purpose**: Scans market for trading candidates.

#### `__init__(self, spy_instance: PriceSpy)`
Stores reference to PriceSpy instance.

#### `scan_market(self, limit=35, callback, logger) -> list`
Delegates to `spy.get_top_symbols(limit=35)`. Returns list of `{symbol, volume}` dicts sorted by volume descending.

---

### 5.5 Strategist (job_analysis.py)

**Purpose**: AI-powered market analysis using Google Gemini.

#### `__init__(self)`
- Configures Gemini API key.
- Calls `_select_best_model()` to pick optimal Gemini model.
- Initializes circuit breaker (`failure_threshold=3`, `timeout=90s`).

#### `_select_best_model(self) -> GenerativeModel`
Tries models in preference order:
1. `gemini-2.0-flash-exp`
2. `gemini-2.0-flash`
3. `gemini-1.5-flash-latest`
4. `gemini-1.5-flash`
5. `gemini-1.5-pro`
6. `gemini-pro`

Falls back to `gemini-1.5-flash` if none available. Saves selected model name to `bot_config.AI_MODEL`.

#### `analyze_market(self, snapshot_id, asset_symbol, tech_data) -> dict`
**Retries**: 3 attempts, 2s wait between.

**Prompt construction**:
- Role: "Senior Crypto Trader & Risk Analyst"
- Input: Asset symbol + technical data JSON (last 5 rows of: close, open, high, low, volume, rsi, macd, signal, ema_20, ema_50, atr).
- Tasks: Evaluate trend via RSI/MACD/ATR, assign sentiment score (-1.0 to 1.0), confidence (0-100%), reasoning, recommendation (BUY/SELL/WAIT).

**Output format**:
```json
{
    "sentiment_score": float,   // -1.0 to 1.0
    "confidence": int,          // 0-100
    "reasoning": "string",
    "recommendation": "BUY" | "SELL" | "WAIT"
}
```

**Fallback on error**: Returns `{sentiment: 0.0, confidence: 0, recommendation: "WAIT"}`.

#### `generate_performance_report(self, trade_history, days_range) -> str`
Sends trade history to Gemini with a "Portfolio Manager" prompt. Returns markdown-formatted performance review.

---

### 5.6 Judge (job_analysis.py)

**Purpose**: Rule-based trade validation and position sizing.

#### `__init__(self)`
- Initializes DB connection.
- Loads config via `_load_config()`.

#### `_load_config(self) -> dict`
Reads all rows from `bot_config` table into a `{key: value}` dict. Strips literal quotes from all values. Fallback defaults: `RSI_THRESHOLD=75`, `AI_CONF_THRESHOLD=60`.

#### `reload_config(self)`
Re-reads config from DB. Called on-demand.

#### `evaluate(self, ai_data, tech_data, portfolio_balance, is_sim=False) -> TradeDecision`

**Evaluation pipeline (in order):**

**Step 0 - Max Positions Check** (BUY only, SELL always allowed):
- Reads `MAX_OPEN_POSITIONS` config (default 5).
- Counts open positions for current mode (`is_sim`).
- Rejects if `current_count >= max_positions`.

**Step 1 - Hard Guardrails:**

| Rule | Config Key | Default | Logic |
|------|-----------|---------|-------|
| RSI Veto | `RSI_THRESHOLD` | 75 | Reject BUY if `RSI > threshold` |
| EMA Trend | `ENABLE_EMA_TREND` | false | Reject BUY if `close < EMA_50` (when enabled) |
| MACD Momentum | `ENABLE_MACD_MOMENTUM` | false | Reject BUY if `MACD < MACD_signal` (when enabled) |

**Step 2 - AI Confidence Check:**
- Reads `AI_CONF_THRESHOLD` (default 60).
- Rejects if `ai_confidence < threshold`.
- Rejects if recommendation is `WAIT` or `HOLD`.

**Step 3 - Position Sizing Calculation:**
```
pos_size_pct = POSITION_SIZE_PCT / 100          (default: 5%)
calculated_size = portfolio_balance * pos_size_pct

max_risk_pct = MAX_RISK_PER_TRADE / 100         (default: 10%)
max_risk_amount = portfolio_balance * max_risk_pct

final_size = min(calculated_size, max_risk_amount)
```

Returns `TradeDecision(decision="APPROVED", size=final_size, reason=...)`.

---

### 5.7 SniperExecutor (job_executor.py)

**Purpose**: Executes buy/sell orders on the exchange.

#### `__init__(self, spy_instance: PriceSpy)`
- Reuses PriceSpy's CCXT exchange instance to avoid duplicate connections.
- Stores DB reference.

#### `execute_order(self, signal) -> bool`

**Input signal dict**: `{assets: {symbol}, signal_type, order_size, asset_id, entry_atr, id}`.

**Mode determination**: Reads `TRADING_MODE` from DB. `"PAPER"` = simulation, otherwise live.

**Simulation Mode (PAPER):**

- Fetches real-time price via `exchange.fetch_ticker()`.
- Uses thread lock (`_sim_balance_lock`) for concurrent safety.
- **BUY**:
  - `cost = order_size` (USDT from Judge).
  - Checks `simulation_portfolio.balance >= cost`.
  - `new_balance = current_balance - cost`.
  - `fill_amount = cost / fill_price` (converts USDT to asset quantity).
  - Updates simulation portfolio balance.
- **SELL**:
  - Finds most recent open simulation position for the asset.
  - `revenue = position_quantity * fill_price`.
  - `new_balance = current_balance + revenue`.
  - Closes the position (`is_open = False`).

**Live Mode:**

- **BUY**: Places market order using `quoteOrderQty` (spend exact USDT amount).
  ```python
  exchange.create_order(symbol, 'market', 'buy', amount, None, {
      'quoteOrderQty': cost_to_precision(symbol, amount),
      'type': 'spot'
  })
  ```
- **SELL**: Looks up open live position quantity, places market sell for that quantity.
  ```python
  exchange.create_order(symbol, 'market', 'sell', sell_qty, None, {'type': 'spot'})
  ```

**Post-execution (both modes):**

- **BUY**: Inserts new position record: `{asset_id, side="LONG", entry_avg=fill_price, quantity=fill_amount, is_open=True, is_sim, highest_price_seen=fill_price, entry_atr}`.
- **SELL**: Marks existing position as `is_open = False`.
- Updates signal status to `"EXECUTED"` or `"FAILED"`.

---

### 5.8 WalletSync (job_wallet.py)

**Purpose**: Syncs Binance wallet balance to database for dashboard display.

#### `__init__(self, db, exchange)`
Stores DB and exchange references. Logs initialization.

#### `sync_wallet(self) -> bool`

1. **Fetch balance**:
   - **Binance TH**: Uses raw `privateGetAccount()` API call (bypasses CCXT margin logic). Parses `balances` array for `free` and `locked` amounts.
   - **Other**: Standard `exchange.fetch_balance({'type': 'spot'})`.

2. **Calculate USD values**:
   - For each non-zero asset:
     - If asset is `USDT`: `usd_value = amount`.
     - Otherwise: Fetches `{ASSET}/USDT` price.
       - **Binance TH**: Direct HTTP request to `api.binance.th/api/v1/ticker/price?symbol={ASSET}USDT`. Falls back to `ticker/24hr` endpoint.
       - **Other**: `exchange.fetch_ticker()`.
     - `usd_value = amount * price`.

3. **Update database**:
   - Deletes all existing records from `wallet_balance` table.
   - Inserts fresh records: `{asset, free, locked, total, usd_value, is_active}`.

4. Logs total USDT amount to `system_logs`.

#### `get_total_balance_usd(self) -> float`
Reads `wallet_balance` table, sums `total` for all USDT entries only. Returns approximate USD total.

---

## 6. Utility Modules (src/utils/)

### 6.1 SimpleCache (cache.py)

**Thread-safe in-memory LRU cache with TTL.**

| Method | Description |
|--------|-------------|
| `get(key)` | Returns cached value or `None` if expired/missing. Tracks hits/misses. |
| `set(key, value, ttl)` | Stores value with TTL. Evicts oldest entry if `max_size` exceeded. |
| `delete(key)` | Removes single entry. |
| `clear()` | Clears all entries and resets stats. |
| `cleanup_expired()` | Removes all expired entries. |
| `get_stats()` | Returns `{hits, misses, hit_rate, size, max_size}`. |

**Implementation**: Uses `OrderedDict` with `(value, expiry_time)` tuples. LRU eviction via `move_to_end()` on access and `popitem(last=False)` on overflow.

### 6.2 RateLimiter (rate_limiter.py)

**Token bucket rate limiter.**

| Method | Description |
|--------|-------------|
| `allow()` | Returns `True` if call permitted. Prunes old timestamps outside the window. |
| `wait_if_needed(timeout)` | Blocks until allowed or timeout. Polls every 0.1s. |
| `get_wait_time()` | Returns seconds until next call allowed, or `None` if immediate. |
| `get_stats()` | Returns `{hits, blocks, current_calls_in_window, limit, period, utilization}`. |

**Algorithm**: Maintains a list of call timestamps. Allows call if `len(recent_calls) < max_calls`. Prunes calls older than `period` seconds.

### 6.3 CircuitBreaker (circuit_breaker.py)

**Prevents cascading failures to external services.**

**States:**
- `CLOSED` - Normal operation. Resets failure count on success.
- `OPEN` - Failure threshold reached. Rejects all calls with `CircuitBreakerOpenError`.
- `HALF_OPEN` - After timeout, allows test calls. Closes on `success_threshold` successes, reopens on any failure.

| Parameter | Description |
|-----------|-------------|
| `failure_threshold` | Consecutive failures before opening (default: 5) |
| `timeout` | Seconds to wait before HALF_OPEN (default: 60) |
| `success_threshold` | Successes needed to close from HALF_OPEN (default: 2) |

**Usage in codebase:**
- `CCXT_API` breaker: threshold=5, timeout=60s (PriceSpy)
- `GEMINI_AI` breaker: threshold=3, timeout=90s (Strategist)

### 6.4 Retry Logic (retry.py)

#### `retry_with_backoff(max_attempts, min_wait, max_wait, exceptions)`
Decorator using tenacity. Exponential backoff between retries. Default: 3 attempts, 1-10s wait, retries on `ExternalAPIError`.

#### `retry_db_operation(max_attempts)`
Specialized for DB operations. Shorter retry window: 2 attempts, 0.5-2s wait. Retries on `DatabaseError`, `ConnectionError`, `TimeoutError`.

#### `safe_execute(func, fallback, error_context)`
Executes function, returns `fallback` on any exception. Never raises.

### 6.5 Custom Exceptions (errors.py)

| Exception | Parent | Use Case |
|-----------|--------|----------|
| `TradingBotError` | `Exception` | Base class. Includes `context` dict for rich error info. |
| `DatabaseError` | `TradingBotError` | DB connection/query failures |
| `ExternalAPIError` | `TradingBotError` | CCXT, Gemini API failures |
| `CircuitBreakerOpenError` | `TradingBotError` | Circuit breaker rejecting calls |
| `ConfigurationError` | `TradingBotError` | Missing env vars or config |
| `ValidationError` | `TradingBotError` | Data validation failures |
| `InsufficientBalanceError` | `TradingBotError` | Balance too low for trade |

### 6.6 Structured Logger (logger.py)

**JSON-formatted logging with context fields.**

- `StructuredLogger`: Wraps Python `logging` with JSON output including timestamp, level, role, and arbitrary context fields.
- `JSONFormatter`: Formats log records as JSON strings.
- `log_execution_time(logger, operation)`: Decorator that logs function duration in milliseconds.
- `get_logger(name, role)`: Factory with global logger cache to avoid duplicates.

### 6.7 AuditLogger (audit_logger.py)

**Logs sensitive operations to `audit_log` database table.**

| Method | Event Type | What It Logs |
|--------|------------|-------------|
| `log_order()` | `ORDER_EXECUTED` | symbol, side, amount, price, is_sim |
| `log_config_change()` | `CONFIG_CHANGED` | key, old_value, new_value, user |
| `log_balance_change()` | `BALANCE_CHANGED` | amount, balance_before, balance_after, reason |
| `log_signal_created()` | `SIGNAL_CREATED` | symbol, signal_type, status, reason |

All methods write to DB and Python logger. Failures in audit logging never crash the main operation.

---

## 7. Database Layer (src/database.py)

### 7.1 `Database` (Singleton)
- Creates Supabase client using `SUPABASE_URL` and `SUPABASE_KEY` environment variables.
- Sets 20-second PostgREST timeout to prevent indefinite hangs.
- Singleton pattern: only one instance created.

### 7.2 `get_db() -> Client`
Returns the singleton Supabase client.

### 7.3 `get_config(key, default) -> value`
- Checks in-memory cache first (5-minute TTL, max 100 entries).
- On cache miss: queries `bot_config` table, strips quotes, caches result.
- Decorated with `@retry_db_operation(max_attempts=2)`.

### 7.4 `get_config_safe(key, default) -> value`
Wraps `get_config()` with `safe_execute()`. Never raises, always returns default on error.

---

## 8. Calculation Reference

### 8.1 Technical Indicators

**RSI (Relative Strength Index)** - `pandas_ta.rsi(length=14)`
- Measures momentum on a 0-100 scale.
- Formula: `RSI = 100 - (100 / (1 + RS))` where `RS = avg_gain / avg_loss` over 14 periods.
- Used by Judge: BUY rejected if `RSI > RSI_THRESHOLD` (default 75, overbought).

**EMA (Exponential Moving Average)** - `pandas_ta.ema(length=20|50)`
- Weighted moving average giving more weight to recent prices.
- Formula: `EMA_today = close * k + EMA_yesterday * (1 - k)` where `k = 2 / (length + 1)`.
- Used by Judge: BUY rejected if `close < EMA_50` (when `ENABLE_EMA_TREND=true`).

**MACD (Moving Average Convergence Divergence)** - `pandas_ta.macd(fast=12, slow=26, signal=9)`
- `MACD Line = EMA(12) - EMA(26)`
- `Signal Line = EMA(9) of MACD Line`
- Used by Judge: BUY rejected if `MACD < Signal` (when `ENABLE_MACD_MOMENTUM=true`).

**ATR (Average True Range)** - `pandas_ta.atr(length=14)`
- Measures volatility.
- `True Range = max(high-low, |high-prev_close|, |low-prev_close|)`.
- `ATR = 14-period smoothed average of True Range`.
- Used by trailing stop system for dynamic stop distance.

**Bollinger Bands** - `pandas_ta.bbands(length=20, std=2)`
- `Middle Band = SMA(20)`
- `Upper Band = SMA(20) + 2 * StdDev(20)`
- `Lower Band = SMA(20) - 2 * StdDev(20)`
- Stored in DataFrame but not currently used in Judge logic.

### 8.2 AI Analysis (Gemini)

Input to AI: Last 5 candles of `[close, open, high, low, volume, rsi, macd, signal, ema_20, ema_50, atr]`.

Output: `{sentiment_score: -1.0..1.0, confidence: 0..100, reasoning: str, recommendation: BUY|SELL|WAIT}`.

### 8.3 Position Sizing

```
calculated_size = portfolio_balance * (POSITION_SIZE_PCT / 100)
max_risk_amount = portfolio_balance * (MAX_RISK_PER_TRADE / 100)
final_size = min(calculated_size, max_risk_amount)
```

Example: Balance = $10,000, POSITION_SIZE_PCT = 5%, MAX_RISK_PER_TRADE = 10%
- calculated_size = $500
- max_risk_amount = $1,000
- final_size = $500

### 8.4 Simulation Trade Calculation

**BUY:**
```
cost = order_size (USDT from Judge)
new_balance = current_balance - cost
quantity = cost / current_price
```

**SELL:**
```
revenue = position_quantity * current_price
new_balance = current_balance + revenue
```

### 8.5 Trailing Stop Calculation

**Activation condition:**
```
profit_pct = (highest_price_seen - entry_price) / entry_price
activated = profit_pct >= MIN_PROFIT_TO_TRAIL_PCT / 100   (default 1%)
```

**ATR-based mode** (`TRAILING_STOP_USE_ATR = true`):
```
trail_distance = entry_atr * TRAILING_STOP_ATR_MULTIPLIER   (default multiplier: 2.0)
trail_price = highest_price_seen - trail_distance
```

**Fixed percentage mode** (default):
```
trail_price = highest_price_seen * (1 - TRAILING_STOP_PCT / 100)   (default 3%)
```

**Trigger condition:**
```
if current_price <= trail_price:
    execute SELL order
```

---

## 9. Configuration Keys

All configuration is stored in the `bot_config` Supabase table as key-value pairs.

| Key | Default | Description |
|-----|---------|-------------|
| `BOT_STATUS` | (none) | "STOPPED" to halt bot, any other value = running |
| `BOT_STATUS_DETAIL` | (none) | Human-readable status message |
| `TRADING_MODE` | "PAPER" | "PAPER" = simulation, "LIVE" = real trading |
| `TIMEFRAME` | "1h" | OHLCV candle timeframe |
| `TRADING_CYCLE_MINUTES` | 2 | Minutes between trading cycles |
| `FARMING_INTERVAL_HOURS` | 12.0 | Hours between farming scans |
| `ACTIVE_CANDIDATES` | (none) | JSON array of symbol strings |
| `LAST_FARM_TIME` | (none) | Unix timestamp of last farming run |
| `LAST_HEARTBEAT` | (none) | Unix timestamp of last heartbeat |
| `AI_MODEL` | (auto) | Selected Gemini model name |
| `MODE` | (auto) | Current operational mode |
| `RSI_THRESHOLD` | 75 | Maximum RSI for BUY approval |
| `AI_CONF_THRESHOLD` | 60 | Minimum AI confidence % for approval |
| `POSITION_SIZE_PCT` | 5.0 | Position size as % of portfolio |
| `MAX_RISK_PER_TRADE` | 10.0 | Maximum risk per trade as % of portfolio |
| `MAX_OPEN_POSITIONS` | 5 | Maximum concurrent open positions per mode |
| `ENABLE_EMA_TREND` | "false" | Enable EMA-50 trend filter |
| `ENABLE_MACD_MOMENTUM` | "false" | Enable MACD momentum filter |
| `MIN_VOLUME` | 50000 | Minimum 24h volume in USDT for candidates |
| `TRADING_UNIVERSE` | "ALL" | "ALL", "SAFE_LIST", or "TOP_30" |
| `TRAILING_STOP_ENABLED` | (none) | "true" to enable trailing stops |
| `TRAILING_STOP_USE_ATR` | "false" | "true" for ATR-based, "false" for fixed % |
| `TRAILING_STOP_PCT` | 3.0 | Fixed trailing stop percentage |
| `TRAILING_STOP_ATR_MULTIPLIER` | 2.0 | ATR multiplier for dynamic trailing stop |
| `MIN_PROFIT_TO_TRAIL_PCT` | 1.0 | Minimum profit % before trailing stop activates |

---

## 10. Trading Flow Summary

```
[Bot Start]
    |
    v
[Wallet Sync] --> DB: wallet_balance
    |
    v
[Trading Cycle Loop] (every N minutes)
    |
    +---> [Check Trailing Stops] --> May trigger SELL
    |
    +---> [Need Farming?]
    |         |
    |    [YES] --> [Radar Scan] --> [HeadHunter Filter] --> DB: ACTIVE_CANDIDATES
    |         |
    |    [NO]  --> Load candidates from DB
    |
    +---> [For Each Candidate Symbol]
              |
              +---> [PriceSpy: Fetch OHLCV + Calculate Indicators]
              |
              +---> [Strategist: AI Analysis via Gemini]
              |         Output: sentiment, confidence, recommendation
              |
              +---> [Judge: Rule Validation + Position Sizing]
              |         Checks: max positions, RSI, EMA, MACD, AI confidence
              |         Output: APPROVED/REJECTED + size in USDT
              |
              +---> [If APPROVED: Sniper Executes Order]
                        Paper: Simulated with real prices
                        Live: Market order via Binance API
                        Records: positions, trade_signals, system_logs
```

---

*Document generated from source code review of zenith-trading-bot repository.*
*Last updated: 2026-01-28*
