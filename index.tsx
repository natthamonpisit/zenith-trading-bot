import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { createRoot } from "react-dom/client";
import {
  ColorType,
  createChart,
  type CandlestickData,
  type IChartApi,
  type ISeriesApi,
  type Time,
} from "lightweight-charts";
import "./index.css";

type TabId = "overview" | "candidates" | "signals" | "positions" | "chart";

type ApiError = {
  code: string;
  message: string;
  retryable?: boolean;
  details?: Record<string, unknown>;
};

type ApiEnvelope<T> = {
  success: boolean;
  data: T;
  error: ApiError | null;
  meta: {
    request_id: string;
    ts: string;
    version: string;
  };
};

type SummaryData = {
  equity: number;
  daily_pnl: number;
  drawdown_pct: number;
  open_positions: number;
  win_rate: number;
  bot_status: string;
};

type CandidateData = {
  symbol: string;
  screener_rank: number;
  liquidity_score: number;
  tradable: boolean;
  reject_reason: string | null;
};

type SignalData = {
  id: string;
  symbol: string;
  signal_type: "BUY" | "SELL" | "WAIT" | "HOLD";
  confidence: number;
  status: string;
  reason_codes: string[];
};

type PositionData = {
  id: string;
  symbol: string;
  side: string;
  entry_avg: number;
  quantity: number;
  leverage: number;
  unrealized_pnl: number;
  realized_pnl: number;
  is_open: boolean;
  exit_reason: string | null;
  created_at: string | null;
  opened_at: string | null;
  closed_at: string | null;
};

type OrderData = {
  id: string;
  signal_id: string | null;
  symbol: string;
  signal_type: string;
  exchange_order_id: string | null;
  price_filled: number;
  quantity: number;
  fee: number;
  status: string;
  slippage_bps: number | null;
  created_at: string | null;
};

type EventData = {
  id: string;
  level: string;
  role: string;
  message: string;
  created_at: string;
};

type KlineCandle = {
  time: number;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
};

type KlineData = {
  symbol: string;
  tf: string;
  candles: KlineCandle[];
};

type PollResult<T> = {
  data: T | null;
  loading: boolean;
  syncing: boolean;
  error: string | null;
  refresh: () => void;
  lastUpdated: number | null;
};

const TAB_ITEMS: Array<{ id: TabId; label: string }> = [
  { id: "overview", label: "Overview" },
  { id: "candidates", label: "Candidates" },
  { id: "signals", label: "Signals" },
  { id: "positions", label: "Positions" },
  { id: "chart", label: "Chart" },
];

const DEFAULT_SYMBOLS = ["BTC/USDT", "ETH/USDT", "SOL/USDT", "BNB/USDT"];
const TIMEFRAMES = ["1m", "5m", "15m", "1h", "4h", "1d"];

const API_BASE_URL =
  import.meta.env.VITE_API_BASE_URL?.toString().trim() ||
  (typeof window !== "undefined" && window.location.port === "3000"
    ? "http://localhost:8000"
    : typeof window !== "undefined"
      ? window.location.origin
      : "http://localhost:8000");

const API_KEY = import.meta.env.VITE_API_KEY?.toString().trim() || "";

function normalizeTopicSymbol(symbol: string): string {
  return symbol.replace("/", "").toUpperCase();
}

function formatDateTime(value: string | null | undefined): string {
  if (!value) return "-";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return String(value);
  return date.toLocaleString();
}

function formatMoney(value: number): string {
  return value.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

function formatPct(value: number): string {
  return `${value.toFixed(2)}%`;
}

function toErrorMessage(error: unknown): string {
  if (error instanceof Error) return error.message;
  if (typeof error === "string") return error;
  return "Unknown error";
}

async function apiGet<T>(
  path: string,
  params?: Record<string, string | number | boolean | null | undefined>,
): Promise<T> {
  const url = new URL(path, API_BASE_URL);
  for (const [key, value] of Object.entries(params || {})) {
    if (value === undefined || value === null || value === "") continue;
    url.searchParams.set(key, String(value));
  }

  const headers: Record<string, string> = {};
  if (API_KEY) headers["X-API-Key"] = API_KEY;

  const response = await fetch(url.toString(), { headers });
  const body = (await response.json()) as ApiEnvelope<T>;
  if (!response.ok || !body.success) {
    const errorText = body.error?.message || `HTTP ${response.status}`;
    throw new Error(errorText);
  }
  return body.data;
}

function usePollingResource<T>(fetcher: () => Promise<T>, intervalMs: number): PollResult<T> {
  const [data, setData] = useState<T | null>(null);
  const [loading, setLoading] = useState(true);
  const [syncing, setSyncing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [lastUpdated, setLastUpdated] = useState<number | null>(null);

  const hasDataRef = useRef(false);
  const requestSeqRef = useRef(0);

  const runFetch = useCallback(
    async (background: boolean) => {
      const seq = ++requestSeqRef.current;
      if (background && hasDataRef.current) {
        setSyncing(true);
      } else {
        setLoading(true);
      }

      try {
        const nextData = await fetcher();
        if (seq !== requestSeqRef.current) return;
        setData(nextData);
        hasDataRef.current = true;
        setError(null);
        setLastUpdated(Date.now());
      } catch (err) {
        if (seq !== requestSeqRef.current) return;
        setError(toErrorMessage(err));
      } finally {
        if (seq !== requestSeqRef.current) return;
        setLoading(false);
        setSyncing(false);
      }
    },
    [fetcher],
  );

  useEffect(() => {
    hasDataRef.current = false;
    setLoading(true);
    setSyncing(false);
    setError(null);
    runFetch(false);
    const timer = window.setInterval(() => {
      runFetch(true);
    }, intervalMs);
    return () => {
      requestSeqRef.current += 1;
      window.clearInterval(timer);
    };
  }, [intervalMs, runFetch]);

  const refresh = useCallback(() => {
    runFetch(Boolean(hasDataRef.current));
  }, [runFetch]);

  return { data, loading, syncing, error, refresh, lastUpdated };
}

function wsUrlForTopic(topic: string): string {
  const base = new URL(API_BASE_URL);
  const protocol = base.protocol === "https:" ? "wss:" : "ws:";
  const wsUrl = new URL(`${protocol}//${base.host}/ws`);
  wsUrl.searchParams.set("topic", topic);
  if (API_KEY) wsUrl.searchParams.set("token", API_KEY);
  return wsUrl.toString();
}

function useTopicWebSocket(
  topic: string,
  onEvent: (payload: Record<string, unknown>, eventType: string) => void,
  onReconnect?: () => void,
): { status: "connecting" | "connected" | "disconnected" } {
  const [status, setStatus] = useState<"connecting" | "connected" | "disconnected">("connecting");
  const onEventRef = useRef(onEvent);
  const onReconnectRef = useRef(onReconnect);

  onEventRef.current = onEvent;
  onReconnectRef.current = onReconnect;

  useEffect(() => {
    let ws: WebSocket | null = null;
    let retryTimer: number | null = null;
    let closedByClient = false;
    let attempt = 0;

    const connect = () => {
      setStatus("connecting");
      ws = new WebSocket(wsUrlForTopic(topic));

      ws.onopen = () => {
        setStatus("connected");
        if (attempt > 0 && onReconnectRef.current) {
          onReconnectRef.current();
        }
        attempt = 0;
      };

      ws.onmessage = (event) => {
        try {
          const parsed = JSON.parse(event.data) as {
            event_type?: string;
            payload?: Record<string, unknown>;
          };
          if (parsed.event_type && parsed.payload) {
            onEventRef.current(parsed.payload, parsed.event_type);
          }
        } catch {
          // ignore malformed payload
        }
      };

      ws.onclose = () => {
        if (closedByClient) return;
        setStatus("disconnected");
        const baseDelay = Math.min(30000, 1000 * 2 ** attempt);
        const jitter = Math.floor(Math.random() * 450);
        const waitMs = baseDelay + jitter;
        attempt += 1;
        retryTimer = window.setTimeout(connect, waitMs);
      };

      ws.onerror = () => {
        ws?.close();
      };
    };

    connect();

    return () => {
      closedByClient = true;
      if (retryTimer !== null) window.clearTimeout(retryTimer);
      ws?.close();
    };
  }, [topic]);

  return { status };
}

function SummaryCard({
  title,
  value,
  tone = "neutral",
}: {
  title: string;
  value: string;
  tone?: "good" | "bad" | "neutral";
}) {
  return (
    <div className={`kpi-card tone-${tone}`}>
      <div className="kpi-label">{title}</div>
      <div className="kpi-value">{value}</div>
    </div>
  );
}

function ChartPanel({ symbol, tf }: { symbol: string; tf: string }) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const seriesRef = useRef<ISeriesApi<"Candlestick"> | null>(null);
  const [candles, setCandles] = useState<CandlestickData<Time>[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const chartTopic = useMemo(() => `chart.kline.${normalizeTopicSymbol(symbol)}.${tf}`, [symbol, tf]);

  const loadBootstrap = useCallback(async () => {
    setLoading(true);
    try {
      const kline = await apiGet<KlineData>("/api/klines", { symbol, tf, limit: 300 });
      const next = (kline.candles || []).map((item) => ({
        time: item.time as Time,
        open: item.open,
        high: item.high,
        low: item.low,
        close: item.close,
      }));
      setCandles(next);
      setError(null);
    } catch (err) {
      setError(toErrorMessage(err));
    } finally {
      setLoading(false);
    }
  }, [symbol, tf]);

  useEffect(() => {
    loadBootstrap();
  }, [loadBootstrap]);

  const wsStatus = useTopicWebSocket(
    chartTopic,
    (payload, eventType) => {
      if (!eventType.startsWith("chart.kline.")) return;

      const payloadCandles = payload.candles;
      if (Array.isArray(payloadCandles) && payloadCandles.length > 0) {
        const mapped = payloadCandles
          .map((item) => {
            const candle = item as KlineCandle;
            return {
              time: candle.time as Time,
              open: candle.open,
              high: candle.high,
              low: candle.low,
              close: candle.close,
            };
          })
          .filter((item) => Number.isFinite(item.open) && Number.isFinite(item.close));
        setCandles(mapped);
        return;
      }

      const last = payload.kline_last as KlineCandle | undefined;
      if (!last) return;
      const next = {
        time: last.time as Time,
        open: last.open,
        high: last.high,
        low: last.low,
        close: last.close,
      };
      setCandles((prev) => {
        if (prev.length === 0) return [next];
        const cloned = [...prev];
        const lastIdx = cloned.length - 1;
        if (cloned[lastIdx].time === next.time) {
          cloned[lastIdx] = next;
        } else {
          cloned.push(next);
          if (cloned.length > 600) {
            cloned.shift();
          }
        }
        return cloned;
      });
    },
    loadBootstrap,
  );

  useEffect(() => {
    if (!containerRef.current) return;

    const chart = createChart(containerRef.current, {
      width: containerRef.current.clientWidth,
      height: 430,
      layout: { background: { type: ColorType.Solid, color: "#0f172a" }, textColor: "#d4d4d8" },
      grid: {
        vertLines: { color: "rgba(212,212,216,0.08)" },
        horzLines: { color: "rgba(212,212,216,0.08)" },
      },
      rightPriceScale: { borderColor: "rgba(212,212,216,0.2)" },
      timeScale: { borderColor: "rgba(212,212,216,0.2)", timeVisible: true, secondsVisible: false },
      crosshair: {
        vertLine: { color: "rgba(59,130,246,0.35)" },
        horzLine: { color: "rgba(59,130,246,0.35)" },
      },
    });

    const series = chart.addCandlestickSeries({
      upColor: "#10b981",
      downColor: "#ef4444",
      wickUpColor: "#10b981",
      wickDownColor: "#ef4444",
      borderVisible: false,
    });

    const resize = () => {
      if (!containerRef.current) return;
      chart.applyOptions({ width: containerRef.current.clientWidth });
      chart.timeScale().fitContent();
    };

    window.addEventListener("resize", resize);
    chartRef.current = chart;
    seriesRef.current = series;

    return () => {
      window.removeEventListener("resize", resize);
      chart.remove();
      chartRef.current = null;
      seriesRef.current = null;
    };
  }, []);

  useEffect(() => {
    if (!seriesRef.current || candles.length === 0) return;
    seriesRef.current.setData(candles);
    chartRef.current?.timeScale().fitContent();
  }, [candles]);

  return (
    <div className="panel">
      <div className="panel-head">
        <h3>Candlestick</h3>
        <div className="tiny-metadata">
          <span>{symbol}</span>
          <span>{tf}</span>
          <span className={`ws-${wsStatus.status}`}>WS: {wsStatus.status}</span>
        </div>
      </div>
      {error ? <div className="error-banner">{error}</div> : null}
      {loading ? <div className="subtle-status">loading chart...</div> : null}
      <div className="chart-shell" ref={containerRef} />
    </div>
  );
}

function App() {
  const [activeTab, setActiveTab] = useState<TabId>("overview");
  const [mode, setMode] = useState<"PAPER" | "LIVE">("PAPER");
  const [symbol, setSymbol] = useState("BTC/USDT");
  const [tf, setTf] = useState("1h");
  const [sessionId, setSessionId] = useState("");

  const summaryFetcher = useCallback(() => apiGet<SummaryData>("/api/dashboard/summary", { mode }), [mode]);
  const candidatesFetcher = useCallback(() => apiGet<CandidateData[]>("/api/candidates", { limit: 40 }), []);
  const signalsFetcher = useCallback(() => apiGet<SignalData[]>("/api/signals", { limit: 60, symbol }), [symbol]);
  const positionsFetcher = useCallback(
    () => apiGet<PositionData[]>("/api/positions", { limit: 60, symbol, session_id: sessionId }),
    [sessionId, symbol],
  );
  const ordersFetcher = useCallback(() => apiGet<OrderData[]>("/api/orders", { limit: 40, symbol }), [symbol]);
  const eventsFetcher = useCallback(() => apiGet<EventData[]>("/api/events", { limit: 12 }), []);

  const summary = usePollingResource(summaryFetcher, 5000);
  const candidates = usePollingResource(candidatesFetcher, 15000);
  const signals = usePollingResource(signalsFetcher, 7000);
  const positions = usePollingResource(positionsFetcher, 7000);
  const orders = usePollingResource(ordersFetcher, 9000);
  const events = usePollingResource(eventsFetcher, 6000);

  const symbolOptions = useMemo(() => {
    const fromCandidates = (candidates.data || []).map((item) => item.symbol);
    return Array.from(new Set([...DEFAULT_SYMBOLS, ...fromCandidates])).sort();
  }, [candidates.data]);

  return (
    <div className="layout">
      <header className="topbar">
        <div>
          <h1>Zenith Mission Control</h1>
          <p>React dashboard for operations, scan, signals, positions, and chart stream</p>
        </div>
        <div className="topbar-actions">
          <button onClick={summary.refresh}>Refresh</button>
        </div>
      </header>

      <section className="toolbar">
        <label>
          Mode
          <select value={mode} onChange={(event) => setMode(event.target.value as "PAPER" | "LIVE")}>
            <option value="PAPER">PAPER</option>
            <option value="LIVE">LIVE</option>
          </select>
        </label>
        <label>
          Symbol
          <select value={symbol} onChange={(event) => setSymbol(event.target.value)}>
            {symbolOptions.map((item) => (
              <option key={item} value={item}>
                {item}
              </option>
            ))}
          </select>
        </label>
        <label>
          Timeframe
          <select value={tf} onChange={(event) => setTf(event.target.value)}>
            {TIMEFRAMES.map((item) => (
              <option key={item} value={item}>
                {item}
              </option>
            ))}
          </select>
        </label>
        <label>
          Session
          <input
            value={sessionId}
            onChange={(event) => setSessionId(event.target.value)}
            placeholder="optional session id"
          />
        </label>
        <div className="toolbar-note">{summary.syncing ? "syncing..." : summary.lastUpdated ? `updated ${new Date(summary.lastUpdated).toLocaleTimeString()}` : ""}</div>
      </section>

      <nav className="tabbar">
        {TAB_ITEMS.map((item) => (
          <button
            key={item.id}
            className={activeTab === item.id ? "active" : ""}
            onClick={() => setActiveTab(item.id)}
          >
            {item.label}
          </button>
        ))}
      </nav>

      {activeTab === "overview" ? (
        <section className="content">
          {summary.error ? <div className="error-banner">{summary.error}</div> : null}
          <div className="kpi-grid">
            <SummaryCard title="Equity" value={`$${summary.data ? formatMoney(summary.data.equity) : "-"}`} />
            <SummaryCard
              title="Daily PnL"
              value={`$${summary.data ? formatMoney(summary.data.daily_pnl) : "-"}`}
              tone={summary.data && summary.data.daily_pnl < 0 ? "bad" : "good"}
            />
            <SummaryCard
              title="Drawdown"
              value={summary.data ? formatPct(summary.data.drawdown_pct) : "-"}
              tone={summary.data && summary.data.drawdown_pct > 6 ? "bad" : "neutral"}
            />
            <SummaryCard
              title="Win Rate"
              value={summary.data ? formatPct(summary.data.win_rate) : "-"}
              tone={summary.data && summary.data.win_rate >= 50 ? "good" : "bad"}
            />
            <SummaryCard
              title="Open Positions"
              value={summary.data ? String(summary.data.open_positions) : "-"}
              tone="neutral"
            />
            <SummaryCard title="Bot Status" value={summary.data ? summary.data.bot_status : "-"} tone="neutral" />
          </div>

          <div className="panel">
            <div className="panel-head">
              <h3>System Events</h3>
              {events.syncing ? <span className="subtle-status">syncing...</span> : null}
            </div>
            {events.error ? <div className="error-banner">{events.error}</div> : null}
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>Time</th>
                    <th>Level</th>
                    <th>Role</th>
                    <th>Message</th>
                  </tr>
                </thead>
                <tbody>
                  {(events.data || []).map((item) => (
                    <tr key={item.id}>
                      <td>{formatDateTime(item.created_at)}</td>
                      <td>{item.level}</td>
                      <td>{item.role}</td>
                      <td>{item.message}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </section>
      ) : null}

      {activeTab === "candidates" ? (
        <section className="content">
          <div className="panel">
            <div className="panel-head">
              <h3>Candidate Scan</h3>
              {candidates.syncing ? <span className="subtle-status">syncing...</span> : null}
            </div>
            {candidates.error ? <div className="error-banner">{candidates.error}</div> : null}
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>Rank</th>
                    <th>Symbol</th>
                    <th>Liquidity</th>
                    <th>Tradable</th>
                    <th>Reject Reason</th>
                  </tr>
                </thead>
                <tbody>
                  {(candidates.data || []).map((item) => (
                    <tr key={item.symbol}>
                      <td>{item.screener_rank}</td>
                      <td>{item.symbol}</td>
                      <td>{item.liquidity_score.toFixed(1)}</td>
                      <td>{item.tradable ? "YES" : "NO"}</td>
                      <td>{item.reject_reason || "-"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </section>
      ) : null}

      {activeTab === "signals" ? (
        <section className="content">
          <div className="panel">
            <div className="panel-head">
              <h3>Signals</h3>
              {signals.syncing ? <span className="subtle-status">syncing...</span> : null}
            </div>
            {signals.error ? <div className="error-banner">{signals.error}</div> : null}
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>ID</th>
                    <th>Symbol</th>
                    <th>Type</th>
                    <th>Confidence</th>
                    <th>Status</th>
                    <th>Reasons</th>
                  </tr>
                </thead>
                <tbody>
                  {(signals.data || []).map((item) => (
                    <tr key={item.id}>
                      <td className="mono">{item.id.slice(0, 8)}</td>
                      <td>{item.symbol}</td>
                      <td>{item.signal_type}</td>
                      <td>{item.confidence.toFixed(1)}</td>
                      <td>{item.status}</td>
                      <td>{item.reason_codes.join(", ") || "-"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </section>
      ) : null}

      {activeTab === "positions" ? (
        <section className="content two-panels">
          <div className="panel">
            <div className="panel-head">
              <h3>Positions</h3>
              {positions.syncing ? <span className="subtle-status">syncing...</span> : null}
            </div>
            {positions.error ? <div className="error-banner">{positions.error}</div> : null}
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>Symbol</th>
                    <th>Side</th>
                    <th>Entry</th>
                    <th>Qty</th>
                    <th>Unrealized</th>
                    <th>Realized</th>
                    <th>Open</th>
                    <th>Updated</th>
                  </tr>
                </thead>
                <tbody>
                  {(positions.data || []).map((item) => (
                    <tr key={item.id}>
                      <td>{item.symbol}</td>
                      <td>{item.side}</td>
                      <td>{item.entry_avg.toFixed(4)}</td>
                      <td>{item.quantity.toFixed(6)}</td>
                      <td className={item.unrealized_pnl >= 0 ? "good" : "bad"}>{item.unrealized_pnl.toFixed(2)}</td>
                      <td className={item.realized_pnl >= 0 ? "good" : "bad"}>{item.realized_pnl.toFixed(2)}</td>
                      <td>{item.is_open ? "YES" : "NO"}</td>
                      <td>{formatDateTime(item.closed_at || item.opened_at || item.created_at)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>

          <div className="panel">
            <div className="panel-head">
              <h3>Orders</h3>
              {orders.syncing ? <span className="subtle-status">syncing...</span> : null}
            </div>
            {orders.error ? <div className="error-banner">{orders.error}</div> : null}
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>ID</th>
                    <th>Symbol</th>
                    <th>Type</th>
                    <th>Price</th>
                    <th>Qty</th>
                    <th>Fee</th>
                    <th>Slippage(bps)</th>
                    <th>Status</th>
                  </tr>
                </thead>
                <tbody>
                  {(orders.data || []).map((item) => (
                    <tr key={item.id}>
                      <td className="mono">{item.id.slice(0, 8)}</td>
                      <td>{item.symbol}</td>
                      <td>{item.signal_type}</td>
                      <td>{item.price_filled.toFixed(4)}</td>
                      <td>{item.quantity.toFixed(6)}</td>
                      <td>{item.fee.toFixed(4)}</td>
                      <td>{item.slippage_bps !== null ? item.slippage_bps.toFixed(2) : "-"}</td>
                      <td>{item.status}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </section>
      ) : null}

      {activeTab === "chart" ? (
        <section className="content">
          <ChartPanel symbol={symbol} tf={tf} />
        </section>
      ) : null}

      {(summary.loading || candidates.loading) && !summary.data ? (
        <div className="subtle-status page-loading">loading dashboard...</div>
      ) : null}
    </div>
  );
}

const rootElement = document.getElementById("root");
if (!rootElement) {
  throw new Error("Root element not found");
}

createRoot(rootElement).render(<App />);
