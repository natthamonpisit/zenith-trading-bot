# Careful Execution Framework (20 Feb 2026)

## Objective
- ลดความผิดพลาดจากการแก้โค้ดโดยบังคับผ่านขั้นตอนเดียวกันทุกครั้ง
- ทำงานแบบ `plan -> risk check -> implement (small batch) -> verify -> release gate`

## Why This Framework
- โปรเจกต์มีหลายชั้น (`scan`, `score`, `decision`, `execution`, `dashboard`, `DB migration`)
- ความเสี่ยงสูงสุดอยู่ที่ชั้น execution/migration ที่อาจกระทบการเทรดจริง

---

## A) Mandatory Gates (ต้องผ่านทุกครั้ง)

### Gate 1: Planning Gate (ก่อนแตะโค้ด)
- [ ] ระบุขอบเขตงานชัดเจน (in-scope / out-of-scope)
- [ ] ระบุไฟล์ที่กระทบ
- [ ] ระบุ DoD ชัดเจน
- [ ] ระบุ rollback plan

Exit criteria:
- มี checklist ย่อยที่ไม่คลุมเครือ และมีลำดับทำทีละข้อ

### Gate 2: Risk Gate (ก่อน implement)
- [ ] ตรวจ schema compatibility (มี migration/fallback หรือไม่)
- [ ] ตรวจ runtime safety (soft-fail แล้วไม่หยุด trade loop)
- [ ] ตรวจ feature flag (เปิด/ปิดได้)
- [ ] ตรวจ config bounds (มี safe range)

Exit criteria:
- มี mitigation ครบทุก risk ระดับ High

### Gate 3: Implementation Gate (ระหว่างแก้)
- [ ] แก้ทีละ batch เล็ก (1-3 เรื่องต่อรอบ)
- [ ] ทุก batch ต้อง compile/syntax ผ่านก่อนทำ batch ถัดไป
- [ ] ไม่แตะส่วนนอก scope โดยไม่บันทึกเหตุผล

Exit criteria:
- ไม่มี regression ในชุดเทสของส่วนที่แก้

### Gate 4: Verification Gate (หลังแก้)
- [ ] รัน targeted tests
- [ ] รัน regression tests ที่เกี่ยวข้องกับ execution/API
- [ ] ตรวจ `git diff --stat` ว่าไม่ล้น scope

Exit criteria:
- เทสผ่าน และไม่เกิด side effect นอกแผน

### Gate 5: Release Gate (ก่อน push/deploy)
- [ ] มี migration rollout note พร้อม SQL verify
- [ ] สถานะ feature flags ชัดเจน (default ปลอดภัย)
- [ ] มี post-deploy checks list

Exit criteria:
- push ได้โดยมีเอกสารประกอบ rollout ครบ

---

## B) Re-analysis of Current Plan (รอบทบทวนล่าสุด)

### Strengths (สิ่งที่ดีแล้ว)
- มี checklist แยก Phase 1/Phase 2
- มี migration docs สำหรับ rollout
- มี test coverage ค่อนข้างดี (unit + API + flow mocks)
- มี soft-fail หลายจุดเพื่อไม่ให้ล้มทั้ง loop

### Gaps to Watch (ช่องเสี่ยงที่ยังต้องคุม)

#### G-1: Checklist Drift
- `execution_checklist_20_Feb_2026.md` ยังสะท้อนสถานะเก่า (บางข้อยังไม่ mark ตามความจริง)
- Risk: ทีมอ่านสถานะผิด
- Mitigation:
  - update checklist ทุกครั้งหลัง push

#### G-2: Migration Dependency Risk
- ถ้า DB ยังไม่ apply migration ล่าสุด บางฟีเจอร์ Phase 2 จะ degrade
- Risk: behavior ไม่ครบตามคาดแม้ระบบไม่ล้ม
- Mitigation:
  - บังคับ pre-release SQL verify checklist ก่อนเปิด feature

#### G-3: Config Consistency Risk
- การตั้งค่า phase2 มีหลาย key ถ้าขาดบาง key อาจใช้ default ที่ไม่ตรง expectation
- Mitigation:
  - seed config keys + dashboard config page
  - เพิ่ม config sanity checker (future task)

#### G-4: Operational Visibility Risk
- ตอนนี้มี monitor แล้ว แต่ยังไม่มี alert strategy (event summary) สำหรับ TP/SL anomalies
- Mitigation:
  - เพิ่ม event/alert digest ใน step ถัดไป

---

## C) Execution Rules for Next Tasks (ใช้ทันที)

### Rule 1: One-Task-One-Checklist
- งานใหม่ทุกงานต้องมี checklist ก่อนเริ่ม

### Rule 2: Fail-Safe Default
- ฟีเจอร์ใหม่ต้อง default ไปทาง conservative (OFF หรือ soft mode)

### Rule 3: No Silent High-Risk Change
- ถ้าแตะ `main.py`, `job_executor.py`, migration:
  - ต้องระบุ risk/rollback ในข้อความสรุปทุกครั้ง

### Rule 4: Push Only After Gate Pass
- ห้าม push ถ้า compile/test ที่เกี่ยวข้องยังไม่ผ่าน

---

## D) Practical Template (Copy/Paste)

### Plan Header
- Goal:
- Scope:
- Out-of-scope:
- DoD:

### Risk Header
- High:
- Medium:
- Low:
- Mitigation:

### Verification Header
- Compile:
- Targeted tests:
- Regression tests:
- Rollout checks:

---

## E) Immediate Next Action (Recommended)
- [ ] Sync `execution_checklist_20_Feb_2026.md` ให้ตรงสถานะจริงล่าสุด
- [ ] เพิ่ม `config sanity checker` (ตรวจ key สำคัญ/ช่วงค่า) ก่อน cycle รันจริง
- [ ] เพิ่ม alert digest สำหรับ TP1/TP2/trailing anomalies
