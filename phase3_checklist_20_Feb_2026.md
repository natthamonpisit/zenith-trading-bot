# Phase 3 Checklist (20 Feb 2026)

## Objective
- ทำ Phase 3 แบบรอบคอบสูงสุด:
  - `walk-forward validation`
  - `AI advisor tuning (safe mode)`
  - `explainability/reporting`
- ก่อนลงมือ implement ต้องผ่าน 3 ด่าน: `Plan v1 -> Second-review -> Gap closure`

---

## Stage A: Plan v1 (Author Pass)

### A1) Scope Definition
- [x] ระบุ scope ชัดเจน (in-scope / out-of-scope)
- [x] ระบุไฟล์/โมดูลที่จะกระทบ
- [x] ระบุ Definition of Done รายข้อ

### A2) Design Proposal
- [x] วาง architecture ของ walk-forward pipeline
- [x] วาง safety constraints ของ AI tuning (advisor only, no auto-override hard guardrails)
- [x] วาง output explainability ที่ต้องมี (score decomposition, decision reason)

### A3) Risk Proposal
- [x] ระบุ High-risk failure modes อย่างน้อย 3 ข้อ
- [x] ระบุ rollback plan ต่อแต่ละ risk
- [x] ระบุ feature flags ที่ใช้คุม rollout

Exit Criteria (Stage A):
- มี Plan v1 ที่ implement ได้จริงและวัดผลได้

---

## Stage B: Second-review (Independent Checker Pass)

> จำลองว่าเป็น reviewer อีกคนที่ไม่ได้เขียนแผน

### B1) Assumption Audit
- [x] ตรวจ assumptions ว่ามีหลักฐานรองรับหรือไม่
- [x] ระบุ assumption ที่ยังไม่ยืนยัน (unknowns)
- [x] แยก fact vs inference ให้ชัด

### B2) Failure/Regression Audit
- [x] ตรวจจุดพังที่อาจกระทบ execution loop
- [x] ตรวจ compatibility กับ schema เดิม/ข้อมูลเก่า
- [x] ตรวจ test coverage gap ที่ยังไม่มี

### B3) Operational Audit
- [x] ตรวจ rollout steps ว่าปลอดภัยพอ
- [x] ตรวจ observability (metric/log/replay) ครบหรือไม่
- [x] ตรวจ rollback path ว่าทำได้จริง

Exit Criteria (Stage B):
- ออกเอกสาร `Second-review findings` พร้อม severity (High/Medium/Low)

---

## Stage C: Gap Closure (Pre-Implementation Gate)

### C1) Resolve High-severity Gaps
- [x] map High gaps ทั้งหมดไปยัง implementation tasks + test gates
- [x] กำหนดว่าถ้า high gap ยังไม่ปิด ห้ามเชื่อม runtime/live path

### C2) Resolve/Accept Medium Gaps
- [x] ปิด/จัดลำดับ Medium gaps ที่จำเป็น
- [x] Medium ที่เลื่อนได้มี mitigation ชัดเจน

### C3) Final Go/No-Go
- [x] สรุป Go/No-Go decision พร้อมเหตุผล
- [x] ถ้า Go: สร้าง implementation checklist แบบ batch เล็ก

Exit Criteria (Stage C):
- ได้สถานะ `GO` พร้อม checklist implementation ทีละข้อ

---

## Implementation (Only After GO)

### D1) Batch Implementation
- [x] แก้ทีละ batch เล็ก
- [x] ทุก batch ต้อง syntax/compile ผ่านก่อน batch ถัดไป
- [x] ทุก batch ต้องมี test ที่เกี่ยวข้อง

### D2) Verification
- [x] targeted tests ผ่าน
- [x] regression tests ที่เกี่ยวข้องกับ scope ผ่าน
- [x] migration verification ผ่าน (ถ้ามี schema change)

### D3) Release Gate
- [x] rollout notes ครบ
- [x] monitoring checkpoints ครบ
- [x] rollback script/checklist ครบ

---

## Required Artifacts
- [x] `phase3_plan_v1.md`
- [x] `phase3_second_review.md`
- [x] `phase3_gap_closure.md`
- [x] `phase3_implementation_checklist.md`

---

## Status
- [x] Framework defined
- [x] Stage A: Plan v1
- [x] Stage B: Second-review
- [x] Stage C: Gap closure
- [x] Stage D: Implementation
- Current decision: `GO (Controlled)` เฉพาะภายใต้ implementation checklist และ feature flags = OFF by default
- Progress note: Batch 0-5 implementation + migration apply/verify + release docs completed
