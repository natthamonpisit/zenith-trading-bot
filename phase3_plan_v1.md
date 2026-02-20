# Phase 3 Plan v1 (20 Feb 2026)

## Goal
- เดินงาน Phase 3 แบบควบคุมความเสี่ยงสูง:
  - `walk-forward validation`
  - `AI tuning advisor (suggest-only)`
  - `explainability/replay` สำหรับการตัดสินใจ

## Scope

### In Scope
- สร้าง pipeline ทดสอบ time-series split ที่ใช้ข้อมูลจริงจาก telemetry table
- สร้าง advisor ที่เสนอ tuning package แต่ไม่มีสิทธิ์ apply config อัตโนมัติ
- เพิ่ม replay/explainability endpoint สำหรับ score breakdown + decision reason
- เพิ่ม test coverage สำหรับ phase3 flows แบบ deterministic

### Out of Scope
- ไม่เปลี่ยน broker integration และ order execution protocol หลัก
- ไม่เพิ่ม indicator ใหม่ระดับ research-heavy
- ไม่เปิด auto-tune เข้าระบบ live โดยตรง
- ไม่แก้ behavior ของ Phase 1/2 ที่รันใน production loop หากไม่จำเป็น

## Proposed Architecture

### 1) Walk-Forward Engine
- New module: `src/roles/walk_forward.py`
- Input:
  - `feature_snapshots`
  - `signal_scores`
  - `post_trade_attribution`
  - config package ที่ต้องการทดสอบ
- Output:
  - fold-level metrics: `win_rate`, `expectancy`, `max_drawdown`, `profit_factor`
  - aggregate recommendation score

### 2) Tuning Advisor (Safe Mode)
- New module: `src/roles/tuning_advisor.py`
- Advisor สร้าง proposal เท่านั้น (JSON package)
- Deterministic validator ตรวจ:
  - bounds ของแต่ละ key
  - monotonic rules (เช่น liquidity ต่ำห้ามยกคะแนนรวม)
  - guardrails (`max_drawdown`, `min_sample_size`)
- Persist proposal status: `DRAFT -> VALIDATED -> REJECTED -> APPROVED_MANUAL`

### 3) Explainability Layer
- API additions ใน `src/api/server.py`
  - endpoint ดู walk-forward run summary
  - endpoint ดู tuning proposals + validation reasons
  - endpoint ดู score decomposition รายสัญญาณ
- Telemetry access ใน `src/telemetry/tracker.py`

## Data Model Plan
- Migration (new):
  - `walk_forward_runs`
  - `walk_forward_fold_results`
  - `tuning_proposals`
  - `tuning_proposal_validations`
- Index focus:
  - `(created_at, status)` สำหรับ operational monitor
  - `(symbol, timeframe, run_id)` สำหรับ replay lookup

## Feature Flags / Config
- `ENABLE_PHASE3_WALK_FORWARD` (default `false`)
- `ENABLE_TUNING_ADVISOR` (default `false`)
- `ENABLE_EXPLAINABILITY_PHASE3` (default `false`)
- `PHASE3_MIN_SAMPLE_SIZE` (default conservative)
- `PHASE3_MAX_ALLOWED_DRAWDOWN` (hard bound)

## Impacted Files (Planned)
- `src/api/server.py`
- `src/telemetry/tracker.py`
- `src/roles/signal_scoring.py`
- `main.py` (hook แบบ optional/safe mode เท่านั้น)
- `dashboard/ui/*` (phase3 monitor/config)
- `migrations/*phase3*.sql`
- `tests/test_phase3_*.py` (new)

## Batch Implementation Plan

### Batch 1: DB + Contracts
- เพิ่ม migration + tracker methods + API contract schema
- DoD:
  - schema ใช้งานได้
  - read/write basic test ผ่าน

### Batch 2: Walk-Forward Core
- build fold splitter + metrics calculator + run persistence
- DoD:
  - run one backfill job ได้
  - metrics deterministic บน fixture data

### Batch 3: Tuning Advisor + Validator
- สร้าง proposal generator + deterministic validator + status transition
- DoD:
  - invalid proposal ถูก reject พร้อมเหตุผล
  - valid proposal อยู่สถานะรอ manual approve

### Batch 4: Explainability API/UI
- เพิ่ม replay endpoints + dashboard panel
- DoD:
  - operator trace decision path ได้ครบ run-level

### Batch 5: Hardening + Rollout
- targeted tests + regression + feature-flag dry-run
- DoD:
  - เปิด flag ทีละส่วนโดยไม่กระทบ trading loop

## Risks and Rollback

### High Risks
- Data leakage ใน walk-forward split
- Advisor bypass guardrails
- Heavy query load กระทบ runtime

### Rollback Strategy
- ปิด feature flags ทั้งหมดเพื่อกลับสู่ Phase 1/2 behavior
- migration rollback script สำหรับตาราง phase3 (drop safely when empty)
- fallback เป็น read-only mode สำหรับ phase3 endpoints

## Definition of Done (Phase 3 Planning Gate)
- มีแผน batch ที่ทำจริงได้พร้อมไฟล์กระทบ
- มี guardrails/rollback ชัดเจน
- มี test matrix ที่รองรับทุก batch
