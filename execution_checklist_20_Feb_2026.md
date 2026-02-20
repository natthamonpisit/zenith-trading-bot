# Execution Checklist (20 Feb 2026)

## Goal
- ทำระบบให้ไปถึงโครงที่คุยกัน: `universe -> feature store -> scoring -> decision -> execution -> replay`
- ทำแบบ incremental และตรวจสอบได้ทุกขั้น

## Ground Rules
- ไม่ revert งานเดิม
- ทุกข้อมี Definition of Done (DoD)
- ทำทีละข้อ, เทสทีละข้อ, ค่อยไปข้อถัดไป

---

## Phase 1A: Stabilize สิ่งที่เพิ่มแล้ว (ตอนนี้)

### 1) Baseline + Checklist Board
- [x] สร้าง checklist กลางไฟล์นี้
- [x] บันทึกสถานะปัจจุบันว่า Phase 1 coding เสร็จแล้วระดับโค้ด
- DoD:
  - มีไฟล์ checklist กลาง
  - มีลำดับงานชัดเจนข้อย่อยต่อข้อ

### 2) Migration Readiness
- [x] ตรวจว่า migration ใหม่ครอบคลุม index/query path ที่ต้องใช้จริง
- [x] เขียนคู่มือรัน migration + verify query แบบ copy/paste
- [x] เพิ่ม fallback note กรณีตารางยังไม่ถูกสร้าง
- DoD:
  - มี migration checklist + verify SQL พร้อมใช้งาน

### 3) Runtime Safety for New Tables
- [x] ยืนยันว่า bot ยังวิ่งต่อได้แม้ตารางใหม่ยังไม่พร้อม (soft-fail logging)
- [x] ยืนยัน run_id/snapshot_id format สม่ำเสมอทุกจุด
- [x] ยืนยันไม่มีจุดที่ทำให้ order execution หยุดเพราะ scoring insert fail
- DoD:
  - ผ่านทดสอบเชิง flow ว่า failure ของ telemetry ไม่ล้ม trade loop

### 4) Config Hardening (Score)
- [x] กำหนด default keys สำหรับ score config ชัดเจน
- [x] เพิ่มข้อจำกัดช่วงค่า (safe bounds) ในระดับ runtime
- [x] ระบุค่าที่แนะนำสำหรับเริ่มใช้งานจริง
- DoD:
  - เปิด score gate ได้โดยไม่ต้องแก้โค้ดเพิ่ม

### 5) Replay/API Coverage
- [x] เพิ่ม endpoint query ใหม่สำหรับ `feature_snapshot` และ `signal_score`
- [x] เพิ่ม filter สำคัญ (`symbol`, `run_id`, `timeframe`, `limit`)
- [x] ทดสอบ response shape ให้คงมาตรฐาน API envelope
- DoD:
  - dashboard หรือ external tools query replay ใหม่ได้ทันที

### 6) Tests Expansion
- [x] เพิ่ม test telemetry สำหรับ table ใหม่ (insert/query path)
- [x] เพิ่ม integration-ish test flow `process_pair` แบบ mock เพื่อเช็ค score persistence
- [x] รันชุด tests ที่เกี่ยวข้องทั้งหมด
- DoD:
  - ชุด test ของ feature ใหม่ผ่านทั้งหมด

---

## Phase 1B: Config + Explainability (ต่อเนื่อง)

### 7) Dashboard Config (Score Panel)
- [ ] เพิ่ม section ตั้งค่า `MIN_TOTAL_SCORE_TO_CANDIDATE`
- [ ] เพิ่ม toggle `ENABLE_SIGNAL_SCORE_GATE`
- [ ] เพิ่ม inputs weights ราย component
- DoD:
  - ปรับ score behavior ได้จาก UI โดยไม่แก้ env/code

### 8) Candidate Insights Enrichment
- [ ] เพิ่มข้อมูล score ล่าสุดต่อ symbol ใน candidates insight
- [ ] แสดงเหตุผลหลักจาก score notes
- DoD:
  - เห็นได้ว่า symbol ไหนผ่าน/ไม่ผ่าน score threshold เพราะอะไร

---

## Phase 2: Order Plan + TP Ladder

### 9) Order Plan Model
- [ ] เพิ่ม `order_plan` schema (entry/SL/TP/trailing mode)
- [ ] เชื่อม execution ให้รับจาก plan object
- DoD:
  - มีชั้นวางแผนออเดอร์ชัดก่อนยิง order จริง

### 10) TP Ladder + Breakeven
- [ ] เพิ่ม partial TP levels
- [ ] เพิ่ม breakeven promotion rule
- DoD:
  - ปิดกำไรแบบเป็นขั้นและเลื่อน stop ตามแผน

---

## Phase 3: Validation + Tuning

### 11) Walk-forward Validation
- [ ] สร้าง pipeline สำหรับ backtest split แบบ time-series
- [ ] รายงาน metrics (win rate, max DD, expectancy)
- DoD:
  - ใช้ข้อมูลจริงช่วยปรับ threshold/weights อย่างมีหลักฐาน

### 12) AI Advisor for Tuning (Safe Mode)
- [ ] ให้ AI เสนอ config package
- [ ] deterministic validator ตรวจก่อน apply
- DoD:
  - AI ช่วย optimize ได้แต่ไม่ bypass guardrails

---

## Current Execution Status
- [x] Step 1 เสร็จแล้ว (สร้าง execution checklist + วางลำดับงาน)
- [x] Step 2 เสร็จแล้ว: Migration Readiness
- [x] Step 3 เสร็จแล้ว: Runtime Safety for New Tables
- [x] Step 4 เสร็จแล้ว: Config Hardening (Score)
- [x] Step 5 เสร็จแล้ว: Replay/API Coverage
- [x] Step 6 เสร็จแล้ว: Tests Expansion
- [ ] Step 7 กำลังรอเริ่ม: Dashboard Config (Score Panel)
