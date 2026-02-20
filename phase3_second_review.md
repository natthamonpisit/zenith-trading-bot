# Phase 3 Second Review (Independent Checker) - 20 Feb 2026

## Review Intent
- จำลอง reviewer คนที่ 2 เพื่อตรวจแผน `phase3_plan_v1.md`
- โฟกัส: assumption, regression risk, operational safety

## Fact vs Inference

### Facts (ยืนยันจากโค้ด/โครงระบบปัจจุบัน)
- มี telemetry tables และ replay API แล้ว (`ai_decisions`, `rule_evaluations`, `post_trade_attribution`, `order_plans`)
- มี score gating และ config layer ในระบบแล้ว
- execution loop มี soft-fail ในหลายจุดเพื่อลดโอกาสล้มทั้งระบบ

### Inferences (ต้องยืนยันเพิ่ม)
- telemetry ปัจจุบันเพียงพอสำหรับ walk-forward ทุกมิติ
- query load จาก phase3 จะไม่กระทบ runtime loop
- dashboard/operator workflow จะรองรับข้อมูล phase3 โดยไม่ช้า

## Findings (Ordered by Severity)

### [High] F-01: Data Leakage Risk in Walk-Forward
- Observation:
  - ถ้า fold splitter ไม่ lock เวลา train/test ชัด อาจเกิด leakage
- Impact:
  - metrics ดูดีเกินจริง ทำให้ tuning package ผิดทิศทาง
- Required action:
  - บังคับ time-index strict split
  - test case สำหรับ leakage guard

### [High] F-02: Advisor Governance Risk
- Observation:
  - หาก proposal path เชื่อม config save flow โดยไม่มี gate แยก อาจ auto-apply โดยไม่ตั้งใจ
- Impact:
  - risk profile ของระบบเปลี่ยนใน production โดยไม่ผ่านมนุษย์
- Required action:
  - แยก state machine ชัดเจน `APPROVED_MANUAL` ก่อน apply เสมอ
  - audit log ทุก transition

### [High] F-03: Execution Regression Risk from Shared Tables
- Observation:
  - phase3 query อาจชนกับ hot-path tables เดิม
- Impact:
  - latency สูงขึ้นในรอบเทรดหลัก
- Required action:
  - แยก query window จำกัด, index ชัดเจน, limit defaults conservative
  - benchmark query ก่อนเปิด flag

### [Medium] F-04: Metrics Reliability Gap
- Observation:
  - expectancy/profit factor ไวต่อ sample size ต่ำ
- Impact:
  - advisor อาจ bias จากข้อมูลน้อยเกินไป
- Required action:
  - บังคับ `PHASE3_MIN_SAMPLE_SIZE`
  - ติด label `low_confidence` ในผล run

### [Medium] F-05: Config Drift and Auditability
- Observation:
  - phase3 เพิ่ม config keys หลายตัว เสี่ยง drift จากค่าจริงในระบบ
- Impact:
  - debug ยากเมื่อผลเทรดไม่ตรง expectation
- Required action:
  - บันทึก config snapshot ต่อ run และ hash ตรวจย้อนกลับ

### [Low] F-06: Explainability UX Noise
- Observation:
  - ถ้าแสดง decomposition ทั้งหมดพร้อมกันจะอ่านยาก
- Impact:
  - operator ใช้งานจริงได้ไม่เต็มที่
- Required action:
  - แสดง summary ก่อน แล้วค่อย drill-down

## Operational Audit
- Rollout safety:
  - ผ่านในระดับแผน ถ้าเปิดใช้ทีละ flag ตาม batch
- Observability:
  - ต้องเพิ่ม metric อย่างน้อย:
    - `phase3_run_duration_ms`
    - `phase3_validation_reject_count`
    - `phase3_query_error_count`
- Rollback:
  - ใช้งานได้ผ่าน feature flag off + phase3 endpoint read-only fallback

## Review Verdict
- Verdict: `CONDITIONALLY ACCEPTED`
- เงื่อนไขก่อน implement:
  - ปิด High findings ทั้ง 3 ข้อ (F-01, F-02, F-03) ใน checklist implementation
  - เพิ่ม deterministic tests สำหรับ leakage และ governance transitions
