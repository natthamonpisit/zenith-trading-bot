# Phase 1 Migration Rollout Guide

เอกสารนี้ใช้สำหรับ rollout migration ของ Phase 1:
- `universe_snapshot`
- `feature_snapshot`
- `signal_score`

ไฟล์ migration:
- `/Users/natthamonpisit/Coding/zenith-trading-bot/migrations/create_phase1_signal_scoring.sql`

## 1) Apply Migration
รัน SQL ทั้งไฟล์บน Supabase SQL Editor:

```sql
-- copy from:
-- migrations/create_phase1_signal_scoring.sql
```

## 2) Verify Tables Created
```sql
SELECT table_name
FROM information_schema.tables
WHERE table_schema = 'public'
  AND table_name IN ('universe_snapshot', 'feature_snapshot', 'signal_score')
ORDER BY table_name;
```

Expected:
- `feature_snapshot`
- `signal_score`
- `universe_snapshot`

## 3) Verify Indexes
```sql
SELECT indexname, tablename
FROM pg_indexes
WHERE schemaname = 'public'
  AND tablename IN ('universe_snapshot', 'feature_snapshot', 'signal_score')
ORDER BY tablename, indexname;
```

Expected core indexes:
- `idx_universe_snapshot_snapshot_id`
- `idx_universe_snapshot_symbol`
- `idx_universe_snapshot_created_at`
- `idx_feature_snapshot_run_id`
- `idx_feature_snapshot_symbol_tf`
- `idx_signal_score_run_id`
- `idx_signal_score_symbol_tf`

## 4) Smoke Insert/Read Test
```sql
-- Universe snapshot
INSERT INTO universe_snapshot (
  snapshot_id, symbol, asset_class, rank, source, volume, status, whitelist_pass, inclusion_reason, metadata
) VALUES (
  'smoke-001', 'BTC/USDT', 'crypto', 1, 'smoke_test', 1000000, 'WHITELIST', true, 'smoke test', '{"stage":"manual"}'::jsonb
);

-- Feature snapshot
INSERT INTO feature_snapshot (
  run_id, symbol, timeframe, close, volume, quote_volume, rsi, macd, macd_signal, ema_20, ema_50, ema_200, atr, adx, price_position_score, ai_confidence, sentiment_score, features_json
) VALUES (
  'smoke-run-001', 'BTC/USDT', '1h', 60000, 1200, 72000000, 58, 1.2, 0.9, 59500, 59000, 57000, 850, 27, 3, 74, 0.3, '{"source":"smoke"}'::jsonb
);

-- Signal score
INSERT INTO signal_score (
  run_id, symbol, timeframe, total_score, threshold, passed_threshold, component_scores, weighted_scores, weights, notes
) VALUES (
  'smoke-run-001', 'BTC/USDT', '1h', 72.4, 60, true,
  '{"trend":80,"momentum":70}'::jsonb,
  '{"trend":20,"momentum":14}'::jsonb,
  '{"trend":25,"momentum":20}'::jsonb,
  '["smoke test"]'::jsonb
);

SELECT snapshot_id, symbol, rank, created_at
FROM universe_snapshot
WHERE snapshot_id = 'smoke-001';

SELECT run_id, symbol, timeframe, close, rsi, created_at
FROM feature_snapshot
WHERE run_id = 'smoke-run-001';

SELECT run_id, symbol, total_score, passed_threshold, created_at
FROM signal_score
WHERE run_id = 'smoke-run-001';
```

## 5) Cleanup Smoke Rows
```sql
DELETE FROM signal_score WHERE run_id = 'smoke-run-001';
DELETE FROM feature_snapshot WHERE run_id = 'smoke-run-001';
DELETE FROM universe_snapshot WHERE snapshot_id = 'smoke-001';
```

## 6) Runtime Fallback Note
ถ้าตารางใหม่ยังไม่ถูกสร้าง:
- bot จะไม่ล้มทั้ง loop เพราะฝั่ง telemetry ใช้ soft-fail (`try/except`)
- ระบบ trade decision/execution หลักยังทำงานต่อได้
- แนะนำให้ apply migration ให้ครบก่อนเปิดใช้งาน score gate (`ENABLE_SIGNAL_SCORE_GATE=true`)

## 7) Recommended Config (v1)
เริ่มด้วยค่าแนะนำนี้ก่อน แล้วค่อย tuning:

```text
ENABLE_SIGNAL_SCORE_GATE=false
MIN_TOTAL_SCORE_TO_CANDIDATE=60
SCORE_LIQUIDITY_MIN_VOLUME=10000
SCORE_WEIGHT_TREND=25
SCORE_WEIGHT_MOMENTUM=20
SCORE_WEIGHT_VOLATILITY=15
SCORE_WEIGHT_LIQUIDITY=20
SCORE_WEIGHT_STRUCTURE=10
SCORE_WEIGHT_PORTFOLIO=10
```

หมายเหตุ:
- ช่วงค่าปลอดภัยของ weights คือ `0..100` ต่อ component
- ตัวระบบ normalize ตาม sum(weights) อัตโนมัติ
