# ATR-Based Trailing Stop Configuration Guide

## New Config Options

เพิ่ม config ใหม่ใน `bot_config` table ใน Supabase:

### 1. TRAILING_STOP_USE_ATR
**Type**: boolean (string: "true" or "false")  
**Default**: false  
**Description**: เปิดใช้งาน ATR-based trailing stop แทน fixed percentage

**Example**:
```sql
INSERT INTO bot_config (key, value) 
VALUES ('TRAILING_STOP_USE_ATR', 'true')
ON CONFLICT (key) DO UPDATE SET value = 'true';
```

### 2. TRAILING_STOP_ATR_MULTIPLIER
**Type**: float (string)  
**Default**: 2.0  
**Description**: ATR Multiplier สำหรับคำนวณระยะห่างของ trailing stop

**คำนวณ**: `trail_distance = ATR × Multiplier`

**แนะนำ**:
- `1.5` - Tight stop (เหมาะกับ scalping, วิ่งเร็ว)
- `2.0` - Balanced (แนะนำ)
- `3.0` - Loose stop (swing trading, ให้ราคาวิ่งได้เยอะ)

**Example**:
```sql
INSERT INTO bot_config (key, value) 
VALUES ('TRAILING_STOP_ATR_MULTIPLIER', '2.0')
ON CONFLICT (key) DO UPDATE SET value = '2.0';
```

---

## How It Works

### Fixed % Mode (Original)
```
Trail Stop Price = Highest Price × (1 - TRAILING_STOP_PCT)
```
**ปัญหา**: ไม่ปรับตามความผันผวนของตลาด

### ATR Mode (New) ✨
```
ATR = Average True Range (from entry time)
Trail Distance = ATR × TRAILING_STOP_ATR_MULTIPLIER
Trail Stop Price = Highest Price - Trail Distance
```

**ข้อดี**:
- ✅ Dynamic: ปรับตาม volatility ของแต่ละ coin
- ✅ BTC มี ATR สูง → stop ห่างขึ้น (ไม่โดน stop ง่าย)
- ✅ Altcoin มี ATR ต่ำ → stop แน่นขึ้น (ป้องกันความเสี่ยง)

---

## Example Scenario

**BTC/USDT**:
- Entry Price: $50,000
- Entry ATR: $500
- ATR Multiplier: 2.0
- Highest Price Seen: $52,000

**Calculation**:
```
Trail Distance = $500 × 2.0 = $1,000
Trail Stop = $52,000 - $1,000 = $51,000
```

ถ้าราคาตก < $51,000 → Trigger SELL

**vs Fixed 3%**:
```
Trail Stop = $52,000 × (1 - 0.03) = $50,440
```
→ แน่นเกินไป สำหรับ BTC ที่ม volatility สูง!

---

## Configuration Examples

### Conservative (Swing Trading)
```sql
UPDATE bot_config SET value = 'true' WHERE key = 'TRAILING_STOP_USE_ATR';
UPDATE bot_config SET value = '3.0' WHERE key = 'TRAILING_STOP_ATR_MULTIPLIER';
UPDATE bot_config SET value = '2.0' WHERE key = 'MIN_PROFIT_TO_TRAIL_PCT';
```

### Balanced (Recommended)
```sql
UPDATE bot_config SET value = 'true' WHERE key = 'TRAILING_STOP_USE_ATR';
UPDATE bot_config SET value = '2.0' WHERE key = 'TRAILING_STOP_ATR_MULTIPLIER';
UPDATE bot_config SET value = '1.0' WHERE key = 'MIN_PROFIT_TO_TRAIL_PCT';
```

### Aggressive (Scalping)
```sql
UPDATE bot_config SET value = 'true' WHERE key = 'TRAILING_STOP_USE_ATR';
UPDATE bot_config SET value = '1.5' WHERE key = 'TRAILING_STOP_ATR_MULTIPLIER';
UPDATE bot_config SET value = '0.5' WHERE key = 'MIN_PROFIT_TO_TRAIL_PCT';
```

---

## Database Schema Updates

### Required Columns

**`trade_signals` table**:
```sql
ALTER TABLE trade_signals 
ADD COLUMN IF NOT EXISTS entry_atr numeric DEFAULT 0;
```

**`positions` table**:
```sql
ALTER TABLE positions 
ADD COLUMN IF NOT EXISTS entry_atr numeric DEFAULT 0;
```

---

## Testing

1. **เปิด PAPER mode** ก่อนทดสอบ
2. **Set config**:
   ```sql
   UPDATE bot_config SET value = 'true' WHERE key = 'TRAILING_STOP_USE_ATR';
   UPDATE bot_config SET value = '2.0' WHERE key = 'TRAILING_STOP_ATR_MULTIPLIER';
   ```
3. **รัน bot** และ BUY position
4. **ดู logs** จะแสดง:
   ```
   [ATR Trail] BTC/USDT: ATR=500.00, Multiplier=2.0, Distance=$1000.00
   ```
5. **เช็ค position table** ควรเห็น `entry_atr` มีค่า

---

## Fallback Behavior

ถ้า **position ไม่มี ATR data** (old positions):
- ระบบจะใช้ **Fixed %** mode แทนอัตโนมัติ
- แสดง log: `[Fixed Trail Fallback] Using 3.0%`

---

## Benefits Summary

| Feature | Fixed % | ATR-Based |
|---------|---------|-----------|
| Volatility Adaptive | ❌ | ✅ |
| Works for all coins | ⚠️ | ✅ |
| Prevents premature stops | ❌ | ✅ |
| Easy to understand | ✅ | ⚠️ |
| Configuration required | Simple | Medium |

**แนะนำ**: ใช้ ATR-based สำหรับ portfolio ที่มีหลาย coins ที่ volatility ต่างกัน
