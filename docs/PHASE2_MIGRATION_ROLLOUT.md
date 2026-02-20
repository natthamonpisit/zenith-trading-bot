# Phase 2 Migration Rollout Guide

ไฟล์ migration:
- `/Users/natthamonpisit/Coding/zenith-trading-bot/migrations/create_phase2_order_plan.sql`

## 1) Apply Migration
รัน SQL ทั้งไฟล์ใน Supabase SQL Editor

## 2) Verify Tables / Columns
```sql
SELECT table_name
FROM information_schema.tables
WHERE table_schema = 'public'
  AND table_name IN ('order_plans')
ORDER BY table_name;
```

```sql
SELECT column_name
FROM information_schema.columns
WHERE table_schema = 'public'
  AND table_name = 'positions'
  AND column_name IN (
    'order_plan_id',
    'initial_stop_loss',
    'current_stop_loss',
    'take_profit_1',
    'take_profit_2',
    'tp1_partial_pct',
    'tp1_hit',
    'break_even_armed',
    'break_even_price',
    'last_tp_event'
  )
ORDER BY column_name;
```

## 3) Recommended Config Keys
```text
ORDER_PLAN_ENABLED=true
STOP_LOSS_ATR_MULTIPLIER=1.8
MIN_STOP_LOSS_PCT=0.8
ENABLE_TP_LADDER=true
TP1_R_MULTIPLE=1.0
TP2_R_MULTIPLE=2.0
TP1_PARTIAL_PCT=50
BREAKEVEN_BUFFER_PCT=0.1
ORDER_PLAN_TRAILING_MODE=ATR
```

## 4) Runtime Notes
- ถ้า migration ยังไม่พร้อม:
  - ฝั่ง insert ตำแหน่ง (position) จะ fallback ไป legacy payload
  - order_plan status update เป็น soft-fail (ไม่ทำให้ execution หยุด)
- เมื่อ migration พร้อม:
  - BUY จะสร้าง `order_plans`
  - TP1/TP2/breakeven/trailing จะใช้งานผ่าน state ใน `positions`
