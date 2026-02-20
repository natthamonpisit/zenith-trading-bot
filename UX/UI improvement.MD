# UX/UI Improvement Notes (Overview + Candidate Tabs)

Status: Clarification locked + implementation started
Updated: 2026-02-19
Scope: Zenith Mission Control > Tabs `Overview`, `Candidate`

## Implementation status (2026-02-19)
- Completed: Tabs moved to top, command row added (`Mode`, `Bot Status`, `Trading Controls`)
- Completed: `System Events` and `Current Trade` shown side-by-side on `Overview`
- Completed: Status explainability tooltip (`Definition` + `Current reason`)
- Completed: Heartbeat split (`Last heartbeat`, `Heartbeat age`) and new `Uptime since last restart`
- Completed: `Updated` renamed to `Latest update on:`
- Completed: Session moved into collapsed `Advanced filters` as `Session ID filter`
- Completed: `Start / Pause / Stop` controls + safe mode switch (`Apply`, confirm, double confirm for `LIVE`)
- Completed: Candidate tab upgraded with source summary, type gallery, capability matrix, scan summary, scanner logs, and agent map
- Completed: Candidate tab #2 layout pass (`mini status on non-overview`, `4 type universe blocks`, `scanner logs compact`, `reference blocks moved to bottom`)
- Completed: Candidate tab force action `Run Radar Scan (Force)` + backend manual scan endpoint (`/api/candidates/scan`) with multi-asset scan support
- Completed: PAPER mode now always previews multi-asset universe (`crypto`, `stock`, `gold`, `silver`) even when non-crypto live connectors are not configured

## เป้าหมายของเอกสารนี้
- บันทึก feedback หลังเปิดใช้งานจริงจากมุมมอง user
- แยกประเด็นที่ต้องตกลงก่อนลงมือแก้ทีเดียว
- ใช้เป็น checklist สำหรับรอบแก้ UX/UI ถัดไป

## Feedback จากการใช้งานจริง (ตามลำดับ)
1. Layout ฝั่งซ้าย/ขวา ยังไม่ใช้พื้นที่เต็มหน้า
- ต้องการให้ content ใน panel ซ้าย/ขวายาวและบาลานซ์ขึ้น
- ตอนนี้ความรู้สึกคือพื้นที่ใช้งานยังไม่เต็ม และจุดสำคัญยังไม่ชัด

2. System Events / Current Trade placement ยังไม่ตรง expectation
- คาดหวัง: `System Events` อยู่ฝั่งซ้าย, `Current Trade` อยู่ฝั่งขวาใน fold แรก
- สถานะที่เห็น: ต้องเลื่อนลงถึงจะเห็น `Current Trade`
- ผลกระทบ: user มองไม่เห็นภาพรวมการเทรดทันทีที่เข้า

3. First glance focus ยังไม่เด่นพอ
- ตอนเข้า Dashboard ทุกอย่างดูน้ำหนักเท่ากันเกินไป
- ยังไม่มี visual hierarchy ที่บอกว่า "อะไรสำคัญสุดตอนนี้"

3.1 Mode ควรเด่นขึ้น
- `Mode` ต้องมองเห็นง่ายกว่าเดิม (เช่น color state badge/chip)

3.2 Bot Status อ่านไม่เข้าใจ
- ต้องมีคำอธิบายสถานะ เช่น tooltip ผ่าน icon `?` เมื่อ hover
- ควรนิยามแต่ละสถานะให้ user เข้าใจ action ได้ทันที

3.3 Heartbeat ไม่ชัดเจนสำหรับ user
- ปัจจุบัน user งงว่า `14h` หมายถึงอะไร
- ต้องอธิบายว่า heartbeat ใช้เพื่ออะไรในระบบนี้

3.4 ควรมี Uptime
- เสนอเพิ่ม `Uptime` เช่น นับตั้งแต่ restart/reset ล่าสุด

3.5 Label `Updated` ควรเปลี่ยนข้อความ
- เปลี่ยนเป็น `Latest update on:`

4. Config section ใช้งานยาก/เสี่ยงเข้าใจผิด
- ยังไม่ชัดว่าเปลี่ยน `Mode` แล้วเกิดอะไรทันที
- คำถามสำคัญ: จะ trade จริงทันทีไหม
- เสนอให้มีปุ่มควบคุมชัดเจน เช่น `Start / Stop / Pause Trading`

5. Navigation tabs ควรอยู่บนสุด
- `Overview/Candidates/Signals/Positions/Chart` ควรย้ายขึ้นไปบนสุดของหน้าก่อน section อื่น

6. Session field ยังไม่ชัดเจน
- User ไม่เข้าใจว่า `Session` คืออะไร และกระทบการกรอง/ระบบอย่างไร
- ต้องมี helper text สั้นๆ อธิบายการใช้งาน

7. Status banner ควรจัดตำแหน่งใหม่
- ข้อความ `Sniper Phase A: Hunting BUYs ...` อาจย้ายไปฝั่งซ้ายใกล้ `System Events`
- เป้าหมายคือจัดกลุ่ม "สถานะการทำงานระบบ" ให้อยู่โซนเดียวกัน

## Clarification ที่ lock แล้ว
1. Overview layout [LOCKED]
- Desktop ใช้ 2-column คงที่
- สัดส่วน: `System Events 65% / Current Trade 35%`
- `Current Trade` ต้องเห็นใน first fold (ไม่ต้องเลื่อน)
- Mobile ให้ stack และให้ `Current Trade` ขึ้นก่อน `System Events`

2. First-glance priority [LOCKED]
- ย้าย tabs (`Overview/Candidates/Signals/Positions/Chart`) ไปไว้บนสุด
- แถวหลักต้นหน้า: `Mode + Bot Status + Trading Controls`
- เปลี่ยน label เป็น `Latest update on:`
- ย้าย status banner (`Sniper Phase A...`) ไปโซนระบบฝั่งซ้ายใกล้ `System Events`

3. Bot control model [LOCKED]
- เพิ่มปุ่มควบคุมชัดเจน: `Start / Pause / Stop Trading`
- การเปลี่ยน `Mode` ไม่ให้ยิงทันที ต้องผ่าน `Apply + Confirm`
- กรณี `LIVE` ใช้ confirm 2 ชั้น

4. Bot Status explainability (tooltip `?`) [LOCKED]
- Tooltip ต้องมี 2 ส่วน:
- `Definition`: ความหมายของสถานะ
- `Current reason`: เหตุผลของสถานะ ณ ตอนนี้ (สำหรับสถานะที่ไม่ใช่ `ACTIVE`)

- Status dictionary (approved text):
- `ACTIVE` = บอททำงานปกติ
- `DEGRADED` = ทำงานได้แต่มีปัญหาบางส่วน
- `PAUSED` = หยุดส่งออเดอร์ชั่วคราว
- `STOPPED` = หยุดระบบเทรด
- `ERROR` = ระบบล้มเหลว ต้องตรวจ log
- `IDLE` = ยังไม่เริ่มรอบเทรด

- Runtime reason rule:
- สำหรับทุกสถานะที่ไม่ใช่ `ACTIVE` (`DEGRADED/PAUSED/STOPPED/ERROR/IDLE`) ต้องแสดง `Current reason` ชัดเจน
- ตัวอย่างคำถามที่ user ต้องตอบได้ทันที: \"ทำไม degraded\", \"ทำไม paused\"
- แหล่งข้อมูลหลัก: `bot_status_detail` (ถ้าไม่มี ให้ fallback เป็นข้อความมาตรฐาน เช่น `No detailed reason reported`)

5. Heartbeat + Uptime spec [LOCKED]
- Heartbeat แสดง 2 ค่า:
- `Last heartbeat` (เวลา heartbeat ล่าสุด)
- `Heartbeat age` (เวลาห่างจาก heartbeat ล่าสุด)
- เพิ่ม `Uptime since last restart` โดยอิง `BOT_START_TIME`
- เปลี่ยน label จาก `Updated` เป็น `Latest update on:`

6. Session UX [LOCKED]
- ย้าย `Session` เป็น advanced filter (collapsed by default)
- เปลี่ยนชื่อ field เป็น `Session ID filter`
- เพิ่ม helper text: `ว่างไว้ = ใช้ active session ล่าสุด`

## Proposed Implementation Pack (รอ approve)
- P-UX-1: Re-layout Overview (true side-by-side, no below-fold for Current Trade)
- P-UX-2: Strong visual hierarchy (mode/status chips, emphasis blocks)
- P-UX-3: Status explainability (tooltip + status dictionary)
- P-UX-4: Control safety (start/stop/pause with confirmations)
- P-UX-5: Label and copy cleanup (`Latest update on`, session helper text)
- P-UX-6: System-status grouping (move sniper phase/status block to ops rail)

## หมายเหตุ
- Clarification หลัก lock แล้วตามที่ตกลง
- รออนุมัติเริ่ม implementation pack ทีเดียว

---

## Candidate Tab: Feedback ใหม่ (รอ clarify ก่อนแก้)

Status: Clarification locked (ready for implementation)
Date: 2026-02-19

1. จำนวน Candidate ตอนนี้มีน้อย (เห็นแค่ 3 รายการ)
- คำถาม: ทำไมแสดงน้อยกว่าที่คาด
- จุดที่ต้องเช็คก่อนแก้ UI:
- source table ที่ใช้จริง (`fundamental_coins`, `assets`, หรือ source อื่น)
- filter ปัจจุบัน (`status`, `tradable`, `mode`, `limit`)
- รอบการ scan ล่าสุดสำเร็จหรือไม่

2. ต้องแสดงรายละเอียด + log ของ Scanner
- ต้องมีแสดงว่า scan อะไรมา และตัดสินใจเพราะอะไร
- ตัวอย่างที่ต้องมีใน Candidate view:
- `scan_run_id`, `started_at`, `finished_at`, `universe_size`, `passed_count`, `reject_count`
- เหตุผลคัดออกแบบอ่านง่าย (เช่น liquidity ต่ำ, ไม่ผ่าน risk filter, ไม่รองรับ broker ปัจจุบัน)
- แสดงลิงก์/ปุ่มเปิด log ล่าสุดของรอบ scan

3. ต้องอธิบาย 6-agent architecture ชัดเจนใน UI
- ระบุชื่อ agent แต่ละตัว + model ที่ใช้ (ถ้าเป็น AI)
- ถ้าเป็น non-AI ให้ระบุชื่อ function + library หลักที่ใช้
- ต้องมี help text สั้นๆ อธิบายหน้าที่ของ agent นั้น
- ในหน้า Candidate ให้เน้นเฉพาะ agent ที่เกี่ยวกับการหา/คัด candidate

4. ความเข้าใจเรื่องงาน scan เป็น non-AI
- สมมติฐานปัจจุบัน: งานรวบรวมตลาด/คำนวณตัวกรองพื้นฐานเป็น non-AI เป็นหลัก (data fetch + deterministic rules)
- AI ควรใช้ชั้นวิเคราะห์/จัดลำดับ/สรุปเหตุผลเพิ่มเติม
- รอ confirm แนวทาง final ก่อน implement

5. ต้องแสดง Candidate type จากหลายแหล่ง (Crypto/Stock/Gold/Silver ก่อน)
- แนวแสดงผลที่ต้องการ: card gallery หรือ grid ที่เห็นประเภทชัดเจน
- Rule ตาม mode:
- `PAPER`: แสดง universe ทั้งหมดที่ระบบ scan ได้
- `LIVE`: แสดงเฉพาะสินทรัพย์ที่ “เชื่อม API แล้วและเทรดได้จริง”
- ต้องมี “Broker/API capability matrix” ในหน้าเดียวกันว่าต่อแหล่งไหนอยู่บ้าง

6. Paper/Live UX ควรแยกเป็นคนละหน้าไหม
- ประเด็น: โครงหน้าคล้ายกันแต่ข้อจำกัดข้อมูลและ action ต่างกัน
- ตัวเลือกสำหรับรอบ clarify:
- Option A: หน้าเดียว + mode toggle (คุมง่าย, reuse สูง)
- Option B: แยก route (`/candidate-paper`, `/candidate-live`) ชัดเจนกว่าแต่ต้นทุนดูแลสูงกว่า
- รอ lock decision ก่อนเริ่มแก้จริง

## Candidate Clarification ที่ lock แล้ว
1. Root cause “มีแค่ 3 candidates” [LOCKED]
- ปัจจุบัน `/api/candidates` แสดงข้อมูลจาก `fundamental_coins` เป็นหลัก
- ข้อมูลใน DB ตอนนี้มีเพียง 3 แถว จึงเห็น 3 รายการ
- สถานะ: หน้านี้เป็น manual universe view ในสภาพปัจจุบัน ไม่ใช่ full scan universe

2. Scan detail + scanner logs [LOCKED]
- เพิ่มบล็อก `Scan Run Summary` และ `Scanner Logs` ในหน้า Candidate
- แสดงอย่างน้อย: `scan_run_id`, `start_time`, `end_time`, `status`, `universe_size`, `passed_count`, `reject_count`
- แสดงเหตุผลการคัดออกแบบอ่านง่ายจาก log/metadata

3. 6-agent explainability ใน UI [LOCKED]
- ต้องแสดงชื่อ agent + model/function/library + help text
- Agent map ที่ยืนยัน:
- `Radar` (non-AI): `scan_market()` -> `PriceSpy.get_top_symbols()` | `ccxt`
- `HeadHunter` (non-AI): `screen_market()` | Supabase + rule filter
- `Strategist` (AI): `analyze_market()` | MiniMax (`MiniMax-M2.5`) primary, Gemini fallback
- `Judge` (rule-based): `evaluate()` | deterministic risk and guardrails
- `SniperExecutor` (execution): `execute_order()` | `ccxt`
- `PriceSpy` (market data): `fetch_ohlcv()`, `calculate_indicators()` | `ccxt`, `pandas`, `pandas_ta`
- `WalletSync` เป็น service เสริม แสดงในส่วน system/service ไม่ถือเป็น 6-role หลัก

4. Non-AI vs AI responsibility [LOCKED]
- งานกวาดข้อมูลตลาดและคัดกรองพื้นฐานให้เป็น non-AI เป็นหลัก
- AI ใช้ในชั้นตีความ/จัดลำดับ/สรุปเหตุผลเพิ่มเติม

5. Candidate type + mode behavior [LOCKED]
- Candidate view ต้องรองรับอย่างน้อย: `crypto`, `stock`, `gold`, `silver`
- `PAPER`: แสดง universe ทั้งหมดที่ระบบ scan ได้
- `LIVE`: แสดงเฉพาะสินทรัพย์ที่ broker/API เชื่อมแล้วและเทรดได้จริง
- ต้องมี capability matrix ว่าต่อ API/broker อะไรอยู่และรองรับ market type ใด

6. Paper/Live page structure [LOCKED]
- เลือก Option A: หน้าเดียว + mode segment/toggle
- ยังไม่แยก route คนละหน้าในเฟสนี้
- จะพิจารณาแยกหน้าเมื่อ flow แตกต่างกันมากจนต้นทุนความซับซ้อนคุ้มค่า

## Candidate Clarification Checklist (locked)
- [x] Lock สาเหตุ root cause ของ “มีแค่ 3 candidates”
- [x] Lock โครงข้อมูล scan log ที่ต้องโชว์ในหน้า Candidate
- [x] Lock รายชื่อ 6 agents + model/function/library ที่ต้องโชว์ใน UI
- [x] Lock ขอบเขต non-AI vs AI สำหรับ candidate pipeline
- [x] Lock โครง gallery + type taxonomy (`crypto`, `stock`, `gold`, `silver`)
- [x] Lock โครง Paper/Live ว่าหน้าเดียวหรือแยกหน้า

---

## Candidate Tab #2 (Implementation record)

Status: Implemented
Date: 2026-02-19

1. Broker/API Capability Matrix และ Latest Scan Summary ย้ายไปด้านล่างสุด [DONE]
- วางเป็นส่วน `Reference` ด้านล่างสุดของ Candidate tab

2. Full trading controls แสดงเฉพาะหน้า Overview [DONE]
- หน้า non-overview (รวม Candidate) ใช้ `mini status strip` แบบย่อแทน
- แสดงเฉพาะ `Mode`, `Bot Status`, `Latest update on`

3. Candidate focus cards [DONE]
- เพิ่มการ์ด: `Visible Candidates`, `Primary Source`, `Fundamental Universe`, `Assets Active`
- เพิ่ม helper text อธิบายความหมาย และจุดแก้ source (`src/api/candidates.py` + `src/api/server.py` -> `_compute_candidate_insights`)

4. Candidate Universe แยก 4 ประเภท [DONE]
- แยกเป็น 4 blocks: `Crypto`, `Stock`, `Gold`, `Silver`
- แต่ละ block มีตารางย่อยของตัวเอง

5. Scanner Logs อยู่ล่างและ compact [DONE]
- จำกัดแสดง `latest 10` rows
- ลดความสูง panel เพื่อให้เป็น quick health check

6. Candidate-specific Agent Activity [DONE]
- หน้า Candidate แสดงเฉพาะ agent ที่เกี่ยวข้องกับ candidate scope
- โชว์ `model/engine`, `functions`, `last action`, `status`
- ใช้ log ล่าสุดเพื่อคำนวณสถานะ `RUNNING/STANDBY/IDLE`

7. Scan universe and whitelist explainability [DONE]
- ปรับ Radar default limit เป็น `100`
- เพิ่ม `Universe Mode` card และ whitelist column (`PASS/WHITELIST/NEUTRAL/BLACKLIST`) ในตาราง candidate
- Candidate scan แยก logic ไปที่ `src/api/candidates.py` (ลดขนาด `server.py`)
- Global radar scan ใช้ exchange สาธารณะ (`RADAR_SCAN_EXCHANGE_ID`, default `bybit`) เพื่อกวาดกว้างและเร็วกว่า TH loop
