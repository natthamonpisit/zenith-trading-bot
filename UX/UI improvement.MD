# UX/UI Improvement Notes (Overview Tab)

Status: Clarification locked + implementation started
Updated: 2026-02-19
Scope: Zenith Mission Control > Tab `Overview`

## Implementation status (2026-02-19)
- Completed: Tabs moved to top, command row added (`Mode`, `Bot Status`, `Trading Controls`)
- Completed: `System Events` and `Current Trade` shown side-by-side on `Overview`
- Completed: Status explainability tooltip (`Definition` + `Current reason`)
- Completed: Heartbeat split (`Last heartbeat`, `Heartbeat age`) and new `Uptime since last restart`
- Completed: `Updated` renamed to `Latest update on:`
- Completed: Session moved into collapsed `Advanced filters` as `Session ID filter`
- Completed: `Start / Pause / Stop` controls + safe mode switch (`Apply`, confirm, double confirm for `LIVE`)

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
