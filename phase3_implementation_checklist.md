# Phase 3 Implementation Checklist (20 Feb 2026)

## Operating Rule
- ทำทีละ batch
- ผ่าน test ของ batch นั้นก่อนค่อยไป batch ถัดไป
- ถ้าเจอ High gap ใหม่ ให้หยุดและอัปเดต gap register ก่อน

## Batch 0: Preconditions
- [x] ยืนยัน feature flags phase3 default = OFF
- [x] ยืนยัน rollback note ต่อ batch ถูกบันทึก
- [x] lock API contract ที่จะเพิ่ม (request/response shape)

## Batch 1: DB Foundation + Tracker Contract
- [x] เพิ่ม migration phase3 tables:
  - `walk_forward_runs`
  - `walk_forward_fold_results`
  - `tuning_proposals`
  - `tuning_proposal_validations`
- [x] เพิ่ม indexes สำหรับ hot query paths
- [x] เพิ่ม methods ใน `src/telemetry/tracker.py`
- [x] เพิ่ม replay endpoints พื้นฐานใน `src/api/server.py`
- [x] เพิ่ม tests:
  - `tests/test_phase3_tracker.py`
  - `tests/test_phase3_api.py`
- Exit check:
  - [x] migration apply ผ่าน
  - [x] tracker read/write ผ่าน
  - [x] API envelope คงมาตรฐานเดิม

## Batch 2: Walk-Forward Engine (F-01)
- [x] สร้าง `src/roles/walk_forward.py`
- [x] Implement strict time-series splitter
- [x] Implement fold metrics calculator (win rate, expectancy, max DD, PF)
- [x] Persist run + fold results
- [x] เพิ่ม tests:
  - `tests/test_phase3_walk_forward.py` (รวม leakage guard)
- Exit check:
  - [x] leakage tests ผ่าน
  - [x] deterministic metrics บน fixture data ผ่าน

## Batch 3: Tuning Advisor + Governance (F-02, F-04, F-05)
- [x] สร้าง `src/roles/tuning_advisor.py`
- [x] generate proposal package จาก walk-forward output
- [x] deterministic validator:
  - bounds check
  - min sample size check
  - max drawdown guard
- [x] enforce state machine (`DRAFT -> VALIDATED -> REJECTED -> APPROVED_MANUAL`)
- [x] persist config snapshot + hash per proposal/run
- [x] เพิ่ม tests:
  - `tests/test_phase3_tuning_advisor.py`
- Exit check:
  - [x] invalid proposal ถูก reject พร้อม reason
  - [x] ไม่มี auto-apply path

## Batch 4: Explainability + Monitor (F-06)
- [x] เพิ่ม score decomposition endpoint
- [x] เพิ่ม decision reason endpoint (รวม proposal validation reasons)
- [x] เพิ่ม dashboard page phase3 (summary -> drill-down)
- [x] เพิ่ม tests:
  - `tests/test_phase3_explainability.py`
- Exit check:
  - [x] operator trace decision path ได้ครบหนึ่ง run

## Batch 5: Runtime Safety + Performance (F-03)
- [x] limit query windows สำหรับ phase3 endpoints/jobs
- [x] benchmark query/load เทียบ baseline
- [x] เพิ่ม soft-fail behavior (ห้ามหยุด loop หลัก)
- [x] เพิ่ม monitoring counters:
  - `phase3_run_duration_ms`
  - `phase3_validation_reject_count`
  - `phase3_query_error_count`
- Exit check:
  - [x] runtime loop ไม่ regress เกินเกณฑ์ที่กำหนด (targeted/regression tests ที่เกี่ยวข้องผ่าน)

## Final Verification
- [x] รัน targeted tests ของ phase3 ทั้งหมด
- [x] รัน regression ที่แตะ execution/API
- [x] ตรวจ `git diff --stat` ว่าอยู่ใน scope phase3
- [x] update checklist status files ให้ตรงสถานะจริง
  - หมายเหตุ regression suite ทั้งโปรเจกต์มี fail เดิมใน `tests/test_judge.py` ที่ไม่ได้แตะจากงานนี้

## Release Gate
- [x] rollout plan: เปิด flags ทีละตัว
- [x] post-deploy checks list พร้อม threshold
- [x] rollback checklist พร้อมคำสั่งและผู้รับผิดชอบ
  - `/Users/natthamonpisit/Coding/zenith-trading-bot/docs/phase3_rollout_notes_20_Feb_2026.md`
  - `/Users/natthamonpisit/Coding/zenith-trading-bot/docs/phase3_rollback_checklist_20_Feb_2026.md`
