# Discussion: Trade System Design (20 Feb 2026)

## Context
- วันที่สรุป: 20 Feb 2026
- อ้างอิงทิศทางหลักจาก `Direction.md` (AI advisor + deterministic governor)
- ใช้กรอบคิดจาก skill `trading-expert` ร่วมกับสภาพระบบจริงใน repo ปัจจุบัน
- เป้าหมาย: ตอบครบ 8 ประเด็น และระบุชัดว่าอะไร "ใช้ของเดิมได้" vs "ต้องพัฒนาใหม่"

---

## สถานะระบบปัจจุบัน (จากโค้ดที่มี)

### ส่วนที่มีแล้ว (Reuse ได้ทันที)
1. Candidate scan + Screener
- มี `Radar` + `HeadHunter` + policy (`TOP_100`, `WHITELIST_POLICY`, `MIN_VOLUME`) แล้ว
- ไฟล์หลัก: `src/api/candidates.py`, `src/roles/job_scout.py`, `src/roles/job_screener.py`

2. Indicator engine
- มี RSI, MACD, EMA20/50/200, ATR, Bollinger, ADX, slope, price position score
- ไฟล์หลัก: `src/roles/job_price.py`

3. Rule-based decision + sizing
- `Judge.evaluate()` มี hard veto + position sizing + risk cap
- ไฟล์หลัก: `src/roles/job_analysis.py`

4. Execution + trailing stop
- มี `SniperExecutor.execute_order()`
- มี trailing stop loop (`check_trailing_stops()`) รองรับ fixed % และ ATR-based
- ไฟล์หลัก: `src/roles/job_executor.py`, `main.py`

5. Telemetry / Replay
- มี `ai_decisions`, `rule_evaluations`, `post_trade_attribution`
- API replay endpoint มีแล้ว
- ไฟล์หลัก: `src/telemetry/tracker.py`, `src/api/server.py`, `migrations/create_*.sql`

### ช่องว่างสำคัญ (ต้องพัฒนาเพิ่ม)
1. ยังไม่มี "feature store" ระดับ per-symbol/per-timeframe ที่แยกจาก runtime snapshot ชัดเจน
2. ยังไม่มี scoring engine กลางที่ normalize indicator แล้วรวมคะแนนแบบ regime-aware
3. ยังไม่มี TP planner ที่เป็น first-class (ตอนนี้เด่นที่ trailing/exit signal)
4. AI telemetry ตอนนี้เก็บ hash + output เป็นหลัก ยังไม่เก็บ prompt/raw response แบบ audit-ready เต็มรูปแบบ
5. universe ยังเป็น hybrid ระหว่าง scan + config list แต่ยังไม่เป็น layer ที่ optimize แยกตาม asset class

---

## ข้อ 1) ใช้ Top list แทน scan logic ได้ไหม

### คำตอบสั้น
- "ได้บางส่วน" และควรใช้เป็นฐาน
- แต่ไม่ควรใช้ "Top gainer/top performer" อย่างเดียว เพราะ churn สูงและเสี่ยงไล่ราคา

### แนวทางที่แนะนำ
ใช้ 3 ชั้น (ลด resource + ยังคุมคุณภาพ):
1. `Universe L0 (Core Static)`
- รายการแกนหลักที่เทรดสม่ำเสมอ เช่น BTC/ETH และ stock core list

2. `Universe L1 (Dynamic Top Liquidity)`
- Crypto: Top 100 by market cap + minimum liquidity/spread guard
- Stocks: Top 50 ต่อ exchange ตาม liquidity + momentum screen (ไม่ใช่เฉพาะ top gainers)

3. `Universe L2 (Event/Opportunistic)`
- รายการจาก event เฉพาะกิจ (news shock / abnormal volume)

### Reuse ของเดิม
- ใช้ `Radar` + global exchange scan + `HeadHunter` ต่อได้ทันที
- ใช้ capability matrix เดิมในการแยก PAPER/LIVE

### ต้องเพิ่ม
- `universe_source` service + snapshot table (เก็บว่า list รอบนี้มาจากอะไร, rank เกณฑ์ไหน)

---

## ข้อ 2) ดึง indicator ทุก asset แล้วเก็บ DB ควรความถี่เท่าไร

### คำตอบสั้น
- ควรทำ 2 ความถี่ ไม่ใช่ความถี่เดียว

### ความถี่ที่แนะนำ
1. `Universe refresh`
- Crypto: ทุก 1 ชั่วโมง
- Stocks/Gold/Silver: ทุก 4 ชั่วโมง (หรือ sync ตาม market session)

2. `Feature calculation`
- Full universe: ทุก 1 ชั่วโมง (baseline)
- Execution shortlist (เช่น Top 10-20 ที่คะแนนนำ): ทุก 5-15 นาที

3. `Risk/execution checks`
- Trailing/exit guard: ทุก 1-2 นาที (ตอนนี้มีใน loop อยู่แล้ว)

### เหตุผล
- ลด request pressure และยังทัน regime shift
- แยก cost-heavy stage (full universe) กับ latency-sensitive stage (execution shortlist)

### Reuse ของเดิม
- มี `TRADING_CYCLE_MINUTES`, `FARMING_INTERVAL_HOURS` และ trailing loop แล้ว

### ต้องเพิ่ม
- scheduler แยกงานระดับ feature store กับ execution decision ให้ชัด
- table สำหรับเก็บ feature time series แบบ query เร็ว

---

## ข้อ 3) scoring indicator + weighting ควรออกแบบอย่างไร

### คำตอบสั้น
- แนะนำคะแนนรวม `0-100` (เข้าใจง่าย, config ง่าย)
- ไม่แนะนำ fix weight เดียวตลอดตลาด ควรเป็น `regime-aware weights`

### โครงคะแนนที่แนะนำ (ตัวอย่าง v1)
1. Trend (0-25)
- EMA alignment, ADX regime

2. Momentum (0-20)
- RSI zone + MACD direction/divergence

3. Volatility Quality (0-15)
- ATR percentile, volatility expansion/contraction

4. Liquidity & Execution (0-20)
- volume, spread proxy, slippage proxy

5. Structure (0-10)
- support/resistance distance, breakout validity

6. Portfolio Fit (0-10)
- correlation concentration, exposure budget

`total_score = sum(weight_i * normalized_signal_i)`

### ทำไมใช้ 100 ไม่ใช้ 1000
- 1000 ไม่ผิด แต่ noise จากการปรับจูนจะสูงขึ้นโดยไม่เพิ่มคุณค่ามาก
- 100 เพียงพอสำหรับ threshold tuning, A/B test, dashboard explainability

### การตั้ง weight แบบ best practice (เชิงปฏิบัติ)
1. เริ่มจาก equal-ish baseline แล้วปรับด้วย walk-forward
2. บังคับ monotonic constraints (เช่น liquidity แย่ คะแนนรวมต้องไม่สูง)
3. แยก `hard veto` ออกจาก `soft score`
4. ใช้ out-of-sample + time-series split + data-snooping controls

### Reuse ของเดิม
- indicator มีเกือบครบสำหรับสร้าง score v1
- Judge + Rule evaluations มีโครง hard veto แล้ว

### ต้องเพิ่ม
- `signal_scoring` module
- `feature_scores` + `signal_breakdown` table สำหรับ audit ว่าคะแนนมาจากอะไร

---

## ข้อ 4) config ควรปรับได้แค่ threshold หรือราย indicator

### คำตอบสั้น
- ควรมีทั้ง 2 ชั้น

### แบบที่แนะนำ
1. ชั้นกลยุทธ์ (ง่าย)
- `MIN_TOTAL_SCORE_TO_CANDIDATE`
- `MIN_TOTAL_SCORE_TO_ENTRY`

2. ชั้น indicator (ละเอียด)
- threshold ต่อ indicator + weight ต่อ indicator
- เปิด/ปิด indicator ได้

3. guardrail
- จำกัดช่วงค่าที่ปรับได้ (min/max) เพื่อลด misconfiguration

### AI เอามาใช้ได้ไหม
- ได้ และควรใช้แบบ "advisor" ไม่ใช่ auto-apply
- AI เสนอ adjustment package (เช่น RSI threshold +2, trend weight +5%)
- ต้องผ่าน deterministic validation + shadow test ก่อน apply

### Reuse ของเดิม
- `bot_config` มี pattern config key/value ใช้งานอยู่แล้ว

### ต้องเพิ่ม
- schema config สำหรับ per-indicator params
- dry-run simulator สำหรับเทียบผลก่อน apply

---

## ข้อ 5) หลังได้ candidate ต้องทำอะไรถึงจะเข้าซื้อ

### คำตอบสั้น
- พี่เข้าใจถูกหลักแล้ว: ต้องมีชุดเงื่อนไขเข้า (entry setup) แยกจาก candidate filtering

### Pipeline ที่ถูกต้อง
1. Candidate qualification (ผ่าน score + hard veto)
2. Entry setup validation
- โครงสร้างราคา (breakout/pullback/support-resistance)
- momentum confirmation
- volume confirmation
- execution feasibility (spread/slippage/time-to-fill)

3. Order planning
- entry zone, invalidation, stop, take-profit plan

4. Final gate
- portfolio exposure, correlation, session risk budget

### ปัจจัยเทคนิคที่ควรมีใน Entry decision
1. Trend context (EMA/ADX/regime)
2. Momentum context (RSI/MACD/divergence)
3. Volatility context (ATR percentile)
4. Market structure (swing high/low, SR zone)
5. Liquidity/execution (volume + spread)
6. Portfolio constraints (max positions, sector/asset concentration)

### Reuse ของเดิม
- Judge มีหลายข้อแล้ว (RSI/confidence/max positions/duplicate)
- ต้องขยายให้มี structure/execution checks แบบ explicit เพิ่ม

---

## ข้อ 6) AI ช่วยคำนวณ risk/position/sentiment และเก็บ prompt ได้ไหม

### คำตอบสั้น
- ได้ แต่แนะนำให้ deterministic เป็นตัวคำนวณหลักของ size/SL/TP
- AI ใช้ตีความ regime/sentiment และอธิบายเหตุผลเชิงบริบท

### หลักการที่แนะนำ
1. Position sizing + stop distance
- deterministic formula (ATR + risk budget + confidence factor)
- AI ให้ "adjustment hint" ได้ แต่ไม่ควรมีสิทธิ์ override hard cap

2. Sentiment pipeline
- เก็บ macro/market sentiment เป็นรอบ (เช่น ทุก 30-60 นาที)
- map sentiment เข้า `sentiment_score` + confidence + source reliability

3. Prompt/response logging
- ปัจจุบัน `ai_decisions` เก็บ `prompt_hash`/`input_hash` + output
- ถ้าต้อง audit เต็ม: เพิ่ม `ai_prompt_archive` (raw prompt/response, token usage, provider/model, redaction status)

### Reuse ของเดิม
- มี run_id + replay tables แล้ว

### ต้องเพิ่ม
- raw prompt storage (optional encryption + retention policy)
- redaction pipeline (ลบ API key/PII/secret ก่อน persist)

---

## ข้อ 7) ตอนนี้มีส่วนสั่งซื้อ + SL/TP/trailing ครบไหม

### คำตอบสั้น
- มี "execution + trailing stop" แล้ว
- ยังไม่ครบในมุม "TP planner + dynamic bracket management" แบบเป็นระบบเต็ม

### ปัจจุบันมี
1. ส่งคำสั่ง BUY/SELL ได้ (`SniperExecutor`)
2. trailing stop loop มีทั้ง fixed % และ ATR-based
3. ปิด position พร้อมบันทึก `exit_reason` ได้

### ควรเพิ่ม
1. `order_plan` stage
- แยกจาก execution signal ชัดเจน: entry, initial SL, TP ladder, trail mode

2. TP management
- partial take-profit levels
- breakeven promotion หลังผ่าน R multiple ที่กำหนด

3. ความเร็วช่วงผันผวน
- ใช้ websocket price stream สำหรับ monitored symbols
- event-driven trigger แทน polling ทั้ง universe
- เฉพาะ shortlist/open positions เท่านั้นที่ monitor ถี่

---

## ข้อ 8) ออกแบบ DB ตัดสินใจให้ครบแต่เร็วและไม่ซ้ำซ้อน

### คำตอบสั้น
- แยก `Operational store` กับ `Analytics store` ชัดเจน
- ใช้ event + snapshot ร่วมกัน

### โครง DB ที่แนะนำ

#### A) Operational (hot path)
1. `universe_snapshot`
- run_id, asset_class, symbol, rank, source, inclusion_reason

2. `feature_snapshot`
- run_id, symbol, timeframe, indicator_name/value (หรือ JSONB compact)

3. `signal_score`
- run_id, symbol, total_score, score_breakdown_json, passed_threshold

4. `order_plan`
- run_id, symbol, side, entry_rule, stop_rule, tp_rule, risk_budget_used

5. `execution_event`
- order_id, event_type(created/filled/partial/cancel), ts, payload

#### B) Analytics (cold path / replay)
1. `ai_decisions` (มีแล้ว)
2. `rule_evaluations` (มีแล้ว)
3. `post_trade_attribution` (มีแล้ว)
4. `ai_prompt_archive` (เพิ่ม)

### หลักลดซ้ำซ้อน
1. เก็บ value ที่ต้อง query เร็วเป็น column
2. เก็บรายละเอียดลึกเป็น JSONB
3. ใช้ hash key (`input_hash`) กันซ้ำ
4. partition ตามวัน/เดือนสำหรับตาราง event ใหญ่
5. retention policy แยก hot/cold

---

## สรุปแต่ละข้อ (Executive decisions)

1. Top-list strategy: ใช้ได้ แต่ต้องผสม liquidity+tradability guard ไม่ใช้ top gainer ล้วน
2. Indicator frequency: แยก 2 speed (full universe 1h + shortlist 5-15m)
3. Scoring: ใช้ 0-100 + regime-aware weights + hard veto แยกออกจาก soft score
4. Config: มีทั้ง global threshold และ per-indicator config พร้อม safe bounds
5. Entry decision: เพิ่ม entry-setup layer ก่อนส่ง order plan
6. AI role: ให้ AI เป็น advisor ด้าน context/sentiment; deterministic ถือสิทธิ์ risk/execution
7. Execution completeness: มีฐานแล้ว แต่ต้องเพิ่ม TP planner/bracket management และ event-driven monitor
8. DB architecture: แยก operational vs analytics + เพิ่ม feature/signal/order-plan tables + prompt archive

---

## Proposed Implementation Plan

### Phase 1 (เร็วสุด, 1-2 สัปดาห์)
1. เพิ่ม `signal_scoring` module + config keys
2. เพิ่ม tables: `universe_snapshot`, `feature_snapshot`, `signal_score`
3. ปรับ pipeline ให้เขียน breakdown ลง DB

### Phase 2 (2-4 สัปดาห์)
1. เพิ่ม `order_plan` + TP ladder logic
2. เพิ่ม event-driven price monitor สำหรับ open positions
3. เพิ่ม `ai_prompt_archive` + redaction

### Phase 3 (4-8 สัปดาห์)
1. walk-forward validation framework
2. auto-tuning suggestion (AI advisor + deterministic approval)
3. dashboard explainability เพิ่ม: score decomposition + reason graph

---

## Research Notes (Best-practice references)

1. Data snooping / overfitting controls
- White (2000), *A Reality Check for Data Snooping*: https://doi.org/10.1111/1468-0262.00152
- Bailey et al., *The Probability of Backtest Overfitting* (PBO/CSCV): https://scholarworks.wmich.edu/math_pubs/42/

2. Volatility-aware risk scaling
- Moreira & Muir, *Volatility Managed Portfolios*: https://www.nber.org/papers/w22208

3. Time-series validation (หลีกเลี่ยง train on future)
- scikit-learn TimeSeriesSplit docs: https://scikit-learn.org/stable/modules/generated/sklearn.model_selection.TimeSeriesSplit.html

4. Survivorship bias in datasets
- CRSP survivor-bias-free database note: https://www.crsp.org/research/crsp-survivor-bias-free-us-mutual-funds/

5. Exchange/API operational limits (สำคัญต่อ polling frequency)
- Binance Spot WebSocket Streams docs: https://github.com/binance/binance-spot-api-docs/blob/master/web-socket-streams.md
- Binance Spot API rate limit docs: https://github.com/binance/binance-spot-api-docs/blob/master/rest-api.md
- Binance WebSocket API rate limit docs: https://github.com/binance/binance-spot-api-docs/blob/master/web-socket-api.md

6. Coin market list endpoint (ใช้ทำ top universe feed)
- CoinGecko coins/markets reference: https://docs.coingecko.com/reference/coins-markets

---

## Final Recommendation
- แนวคิดพี่ไปถูกทางมาก และต่อยอดจากของเดิมได้เยอะ
- ถ้าต้องเลือก "จุดคุ้มค่าที่สุด" ตอนนี้: ทำ `scoring + feature store + order_plan` ก่อน
- หลังจากนั้นค่อยยกระดับ AI tuning และ full explainability เพราะฐานข้อมูลจะพร้อมรองรับแล้ว
