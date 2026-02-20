# Phase 2 Checklist (20 Feb 2026)

## Scope
- เพิ่ม `order_plan` layer ก่อน execution
- เพิ่ม `TP ladder` (TP1 partial + TP2 exit)
- เพิ่ม `breakeven promotion` และผูกกับ trailing stop

## Gap Analysis (Current Code)

### G1: No first-class order plan object/table
- ตอนนี้ `process_pair()` ส่ง `trade_signals` ตรงไป executor
- ยังไม่มี persistence ชั้น `order_plan` ที่บอกโครง entry/SL/TP/trailing mode อย่างชัด

### G2: TP planner ยังไม่เป็นระบบ
- มี trailing stop แล้วใน `check_trailing_stops()`
- แต่ยังไม่มี TP1/TP2 logic และไม่มี partial take-profit

### G3: Breakeven promotion ยังไม่ explicit
- trailing จะเลื่อนตาม peak แต่ยังไม่มี rule ย้าย stop ไป break-even เมื่อถึง milestone

### G4: Position schema ยังขาด field แผน
- ยังไม่มี columns มาตรฐานสำหรับ `initial_stop_loss/current_stop_loss/take_profit_1/take_profit_2/tp1_hit`

### G5: Replay visibility ของ phase 2 ยังไม่ครบ
- ตอนนี้ replay หลักมี AI/rule/post-trade + feature/score
- ยังไม่มี view ของ order plan

---

## Implementation Checklist

### 1) Phase 2 DB Foundation
- [x] สร้าง migration: `order_plans` table
- [x] เพิ่ม columns สำหรับ position-level risk/TP state
- [x] เพิ่ม index สำหรับ query hot path (`status`, `symbol`, `run_id`, `created_at`)
- DoD:
  - มี schema รองรับ order plan + TP ladder state พร้อมใช้งาน

### 2) Order Planner Module
- [x] เพิ่ม `src/roles/order_planner.py`
- [x] รองรับ config-driven plan (ATR stop, TP1/TP2 R-multiple, partial %)
- [x] มี fallback ค่า default ถ้า config ไม่ครบ
- DoD:
  - ได้ plan object เดียวที่ deterministic และอธิบายได้

### 3) Pipeline Integration (Main Flow)
- [x] `process_pair()` สร้าง order plan สำหรับ BUY
- [x] persist order plan ลง DB และผูกกับ signal/run
- [x] แนบค่า SL/TP ลง signal payload ที่ส่ง Sniper
- DoD:
  - ทุก BUY ที่ผ่าน Judge มี plan record และ payload พร้อม execution

### 4) Executor Integration
- [x] BUY: persist plan fields ลง `positions`
- [x] SELL: รองรับ partial close (`partial_close_pct`) สำหรับ TP1
- [x] sync `order_plans.status` เมื่อ position เปิด/ปิด
- DoD:
  - partial TP ทำงานจริง และสถานะแผนใน DB ตาม lifecycle

### 5) TP Ladder + Breakeven in Runtime Monitor
- [x] เพิ่ม TP2 full-exit trigger
- [x] เพิ่ม TP1 partial trigger + mark `tp1_hit`
- [x] เพิ่ม breakeven floor ผสาน trailing stop
- DoD:
  - มี exit orchestration ครบ: TP1 partial -> breakeven/trailing -> TP2/stop

### 6) Replay/API + Tests
- [x] เพิ่ม replay endpoint สำหรับ order plans
- [x] เพิ่ม unit tests สำหรับ order planner
- [x] เพิ่ม test flow ขั้นพื้นฐานของ phase2 execution path
- DoD:
  - query/order-plan replay ได้ และ test ผ่าน

### 7) Dashboard Config for Phase 2
- [x] เพิ่ม controls สำหรับ ORDER_PLAN/TP ladder/breakeven ในหน้า Strategy Config
- [x] ผูกค่ากับ save flow เดิมใน `bot_config`
- DoD:
  - ปรับพารามิเตอร์ Phase 2 ได้จาก UI โดยไม่แก้โค้ด

### 8) Order Plan Monitor Page
- [x] เพิ่มหน้า dashboard สำหรับ monitor `order_plans`
- [x] แสดง filters + metrics + linked open positions
- [x] เพิ่ม route + sidebar navigation
- DoD:
  - operator เห็น lifecycle ของ plan/position ได้จาก dashboard

---

## Status
- [x] Checklist + gap analysis done
- [x] Step 1 done: Phase 2 DB Foundation
- [x] Step 2 done: Order Planner Module
- [x] Step 3 done: Pipeline Integration
- [x] Step 4 done: Executor Integration
- [x] Step 5 done: TP Ladder + Breakeven Monitor
- [x] Step 6 done: Replay/API + Tests
- [x] Step 7 done: Dashboard Config for Phase 2
- [x] Step 8 done: Order Plan Monitor Page
