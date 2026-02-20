# Phase 3 Gap Closure (Pre-Implementation Gate) - 20 Feb 2026

## Input
- Plan: `phase3_plan_v1.md`
- Second review: `phase3_second_review.md`

## Gap Register

| Gap ID | Severity | Issue | Mitigation | Exit Criteria | Status |
|---|---|---|---|---|---|
| F-01 | High | Data leakage in walk-forward split | Implement strict time split + add leakage test fixtures | `test_phase3_walk_forward.py` มี test leakage guard ผ่าน | Planned |
| F-02 | High | Advisor may bypass manual governance | Enforce proposal state machine + prohibit direct apply path | ไม่มี path apply ได้ถ้าไม่ `APPROVED_MANUAL` และมี audit log | Planned |
| F-03 | High | Query load regression on runtime tables | Add indexes, bounded query windows, conservative limits, benchmark | benchmark query ผ่าน threshold และ runtime loop ไม่ช้าลงผิดปกติ | Planned |
| F-04 | Medium | Metrics unstable when sample size low | Add `PHASE3_MIN_SAMPLE_SIZE` + `low_confidence` flag | run ต่ำกว่าเกณฑ์จะไม่ปล่อย suggestion ปกติ | Planned |
| F-05 | Medium | Config drift / replay mismatch | Persist config snapshot + hash per run | replay สามารถ trace config package ได้ทุก run | Planned |
| F-06 | Low | Explainability UI overload | Summary-first with drill-down | operator อ่าน decision path ได้ใน 1 page | Planned |

## Closure Strategy

### Mandatory Before Any Runtime Hook
- ปิด F-01, F-02, F-03 ให้ครบก่อนเชื่อมเข้า flow หลัก
- ถ้าไม่ครบ ให้ phase3 ทำงานเฉพาะ offline/backfill mode

### Acceptable Deferred (With Mitigation)
- F-06 สามารถเลื่อนไป batch UI ถัดไปได้ ถ้า API explainability พร้อมและใช้งานได้

## Go / No-Go Decision
- Decision: `GO (Controlled, Batch-Scoped)`
- Reason:
  - แผนและรีวิวมี mitigation ครบ
  - ยังไม่เปิด production behavior จนกว่า High gaps จะถูกปิดและ tests ผ่าน

## Guardrails for GO
- default flags ทั้งหมดเป็น `false`
- no auto-apply config from advisor
- hard fail ห้ามกระทบ execution loop; ให้ soft-fail + log เท่านั้น

## Pre-Implementation Acceptance Criteria
- มี implementation checklist ผูกกับ gaps ชัดเจน
- มี test plan สำหรับทุก High gap
- มี rollback note ต่อ batch
