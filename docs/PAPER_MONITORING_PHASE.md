# Paper Mode Monitoring Phase - 7 Day Testing Guide

## Overview

This guide will help you monitor and evaluate the downtrend protection system during a 7-day paper trading test period. Use this to validate the system before moving to live trading or considering exchange migration.

**Testing Period:** 7 days minimum
**Mode:** PAPER trading
**Goal:** Validate downtrend protection effectiveness and overall system performance

---

## 📋 Pre-Test Setup

### Step 1: Verify Configuration

Run this command to check your current settings:
```bash
python3 -c "from src.database import get_db; db = get_db(); print([r for r in db.table('bot_config').select('key,value').in_('key', ['TRADING_MODE', 'ENABLE_DOWNTREND_PROTECTION', 'DOWNTREND_PROTECTION_MODE']).execute().data])"
```

**Expected Output:**
```
TRADING_MODE: PAPER
ENABLE_DOWNTREND_PROTECTION: true
DOWNTREND_PROTECTION_MODE: MODERATE
```

### Step 2: Record Baseline Metrics

**Starting Information:**
```
Date Started: _______________
Starting Balance: $___________
BTC Price: $__________
Current BTC Trend: UPTREND / NEUTRAL / DOWNTREND / STRONG_DOWNTREND
Protection Mode: STRICT / MODERATE / SELECTIVE
```

### Step 3: Enable Monitoring

**Console Monitoring:**
```bash
# If running locally, watch the output
python3 main.py

# Look for these log lines:
# "Market Trend: DOWNTREND (Strength: X%, Confidence: Y%)"
# "REJECTED: Downtrend Protection..."
```

**Dashboard Access:**
- Bookmark: http://localhost:8501 (or your dashboard URL)
- Keep Trade History page open
- Check Config page daily

---

## 📊 Daily Monitoring Checklist

### Morning Routine (5 minutes)

- [ ] Check dashboard Trade History page
- [ ] Note overnight signals (if bot ran overnight)
- [ ] Check current BTC trend in console logs
- [ ] Record paper balance
- [ ] Screenshot dashboard (optional, for records)

### Evening Review (10 minutes)

- [ ] Count total signals for the day
- [ ] Count rejected signals
- [ ] Count executed trades
- [ ] Review closed positions (if any)
- [ ] Update tracking spreadsheet
- [ ] Note any unusual behavior

---

## 📈 Key Metrics to Track

### 1. Trade Activity Metrics

| Metric | How to Find | Target |
|--------|-------------|--------|
| **Total Signals Generated** | Trade History → Count all entries | Baseline comparison |
| **Signals Rejected** | Filter by Status: REJECTED | Should correlate with downtrends |
| **Trades Executed** | Filter by Status: APPROVED → FILLED | Quality over quantity |
| **Win Rate** | Closed Positions → Wins / Total | Should improve (>55%) |
| **Average Trade P&L** | Sum of closed P&L / Count | Positive overall |

### 2. Protection Effectiveness

| Metric | How to Measure | Good Sign |
|--------|----------------|-----------|
| **Downtrend Rejections** | Count "Downtrend Protection" in judge_reason | High during actual drops |
| **False Rejections** | Rejected trades that would have won | Low (<10% of rejections) |
| **Avoided Losses** | Estimate P&L if rejected trades executed | Negative (avoided losses) |
| **Capital Preservation** | Balance stability during BTC drops | Stays flat or up |

### 3. System Performance

| Metric | How to Check | Acceptable Range |
|--------|--------------|------------------|
| **Max Drawdown** | Lowest balance vs peak | <10% with protection |
| **Current Balance** | Dashboard → Simulation Portfolio | Trending up |
| **Open Positions** | Dashboard → Active Positions | Within MAX_OPEN_POSITIONS |
| **Trailing Stop Hits** | Count exit_reason: TRAILING_STOP | Working as expected |

---

## 📝 Daily Tracking Template

### Option 1: Simple Spreadsheet

Create a Google Sheet or Excel file with these columns:

```
| Date | Day | BTC Trend | BTC Price | Signals | Rejected | Executed | Wins | Losses | Paper Balance | Change | Notes |
|------|-----|-----------|-----------|---------|----------|----------|------|--------|---------------|--------|-------|
| 1/29 | 1   | DOWN      | $88,069   | 5       | 4        | 1        | 0    | 0      | $1,000        | $0     | 4 correctly rejected |
| 1/30 | 2   | DOWN      | $86,500   | 3       | 3        | 0        | 0    | 0      | $1,000        | $0     | All avoided |
| 1/31 | 3   | NEUTRAL   | $87,200   | 4       | 1        | 3        | 2    | 1      | $1,015        | +$15   | Good bounce trades |
```

### Option 2: Notebook/Journal

```
=== Day 1: January 29, 2025 ===
BTC Trend: STRONG_DOWNTREND
BTC Price: $88,069 → $86,800 (-1.4%)

Signals Today: 5
- Rejected: 4 (Downtrend Protection)
- Executed: 1 (ETH/USDT - partial fill)

Notes:
- Protection working correctly
- BTC below EMA200
- System avoided buying falling BTC, SOL, ADA
- Only allowed ETH which showed relative strength

Balance: $1,000 (unchanged - GOOD!)

---

=== Day 2: January 30, 2025 ===
...
```

---

## 🚦 What to Look For

### ✅ Good Signs (System Working)

**During Downtrends:**
- Most BUY signals are rejected
- Paper balance stays flat or slightly up
- Console shows: "Downtrend Protection (MODERATE): Strong downtrend..."
- Coins that are rejected do drop further in price
- Capital preserved in USDT

**During Uptrends:**
- Normal trading frequency
- Trades execute as usual
- Minimal rejections from downtrend filter
- Profitable trades
- Balance growing

**During Neutral Markets:**
- Slightly fewer trades (more selective)
- Higher quality setups
- Good win rate
- Some rejections (expected)

### 🚩 Red Flags (Needs Tuning)

**Problem Signs:**
- Too many rejections during clear uptrends
- Missing obvious good trades
- Still buying heavily into downtrends
- Win rate decreasing compared to before
- Balance dropping during uptrends
- No rejections during obvious downtrends

**Action Required:**
- Check config settings
- Review `DOWNTREND_PROTECTION_MODE` (try SELECTIVE if STRICT is too conservative)
- Adjust `DOWNTREND_AI_BOOST` (lower = less strict, higher = more strict)
- Verify `ADX_TREND_THRESHOLD` matches market volatility

---

## 🔍 Detailed Analysis Commands

### Check Current Paper Balance
```bash
python3 -c "from src.database import get_db; db = get_db(); result = db.table('simulation_portfolio').select('balance').eq('id', 1).execute(); print(f'Paper Balance: ${float(result.data[0][\"balance\"]):,.2f}')"
```

### Count This Week's Trades
```bash
python3 -c "from src.database import get_db; from datetime import datetime, timedelta; db = get_db(); week_ago = (datetime.now() - timedelta(days=7)).isoformat(); signals = db.table('trade_signals').select('id').gte('created_at', week_ago).execute().data; print(f'Total signals this week: {len(signals)}')"
```

### View Recent Rejections with Reasons
```bash
python3 -c "from src.database import get_db; db = get_db(); rejected = db.table('trade_signals').select('created_at,judge_reason').eq('status', 'REJECTED').order('created_at', desc=True).limit(10).execute().data; print('Recent Rejections:'); [print(f'{r[\"created_at\"][:10]}: {r[\"judge_reason\"]}') for r in rejected]"
```

### Count Downtrend Protection Rejections
```bash
python3 -c "from src.database import get_db; from datetime import datetime, timedelta; db = get_db(); week_ago = (datetime.now() - timedelta(days=7)).isoformat(); rejected = db.table('trade_signals').select('judge_reason').eq('status', 'REJECTED').gte('created_at', week_ago).execute().data; downtrend_rejections = [r for r in rejected if 'Downtrend Protection' in str(r.get('judge_reason', ''))]; print(f'Downtrend rejections: {len(downtrend_rejections)} / {len(rejected)} total rejections')"
```

### Check Win Rate
```bash
python3 -c "from src.database import get_db; from datetime import datetime, timedelta; db = get_db(); week_ago = (datetime.now() - timedelta(days=7)).isoformat(); positions = db.table('positions').select('pnl').eq('is_open', False).gte('closed_at', week_ago).execute().data; wins = len([p for p in positions if p.get('pnl', 0) > 0]); total = len(positions); win_rate = (wins / total * 100) if total > 0 else 0; print(f'Win Rate: {win_rate:.1f}% ({wins} wins / {total} trades)')"
```

### View Top Performers
```bash
python3 -c "from src.database import get_db; from datetime import datetime, timedelta; db = get_db(); week_ago = (datetime.now() - timedelta(days=7)).isoformat(); positions = db.table('positions').select('id, pnl').eq('is_open', False).gte('closed_at', week_ago).order('pnl', desc=True).limit(5).execute().data; print('Top 5 Trades:'); [print(f'Position #{p[\"id\"][:8]}: ${p.get(\"pnl\", 0):+.2f}') for p in positions]"
```

---

## 📊 Mid-Week Check (Day 3-4)

### Performance Review Questions

**1. Is the downtrend protection activating appropriately?**
- [ ] Yes - rejecting during actual downtrends
- [ ] No - not rejecting when it should
- [ ] Too much - rejecting during uptrends

**2. How's the paper balance trending?**
- [ ] Up (positive)
- [ ] Flat (preserved during downtrends - also positive)
- [ ] Down (investigate why)

**3. Are you missing good opportunities?**
- [ ] No - protection mode is balanced
- [ ] Yes - mode too strict (consider SELECTIVE)
- [ ] Unsure - need more data

**4. Win rate vs pre-protection baseline?**
- [ ] Improved (great!)
- [ ] Same (acceptable)
- [ ] Worse (needs tuning)

### Adjustment Decisions

**If too many rejections during uptrends:**
```sql
-- Lower the AI boost requirement
UPDATE bot_config SET value = '10' WHERE key = 'DOWNTREND_AI_BOOST';

-- Or switch to SELECTIVE mode
UPDATE bot_config SET value = 'SELECTIVE' WHERE key = 'DOWNTREND_PROTECTION_MODE';
```

**If not rejecting enough during downtrends:**
```sql
-- Increase AI boost requirement
UPDATE bot_config SET value = '30' WHERE key = 'DOWNTREND_AI_BOOST';

-- Or switch to STRICT mode
UPDATE bot_config SET value = 'STRICT' WHERE key = 'DOWNTREND_PROTECTION_MODE';
```

**If getting whipsawed by choppy markets:**
```sql
-- Raise ADX threshold (only trade strong trends)
UPDATE bot_config SET value = '30' WHERE key = 'ADX_TREND_THRESHOLD';
```

---

## 🎯 End-of-Week Analysis (Day 7)

### Final Performance Report

**Overall Statistics:**
```
Testing Period: ___ to ___
Total Days: 7

Starting Balance: $_________
Ending Balance: $_________
Total Return: ____%
Max Drawdown: ____%

Total Signals: ___
Total Rejected: ___ (___%)
Total Executed: ___ (___%)

Closed Trades: ___
Winning Trades: ___ (___%)
Losing Trades: ___ (___%)
Win Rate: ____%

Total P&L: $_____
Average P&L per Trade: $_____
Best Trade: $_____
Worst Trade: $_____
```

### Downtrend Protection Analysis

**Protection Effectiveness:**
```
Days in UPTREND: ___
Days in DOWNTREND: ___
Days in NEUTRAL: ___

Downtrend Protection Rejections: ___
Other Rejections (RSI, AI, etc.): ___

Estimated Avoided Losses: $_____
(if rejected trades had executed)

Capital Preservation Rate: ____%
(% of balance preserved during downtrends)
```

### Comparison vs Non-Protected Trading

If you have historical data without protection:

| Metric | Without Protection | With Protection | Improvement |
|--------|-------------------|-----------------|-------------|
| Win Rate | ___% | ___% | +___% |
| Max Drawdown | -___% | -___% | +___% |
| Total Return | ___% | ___% | +___% |
| Trades Executed | ___ | ___ | -___% (expected) |

---

## 🤔 Decision Framework

### After 7 Days, Choose Your Path:

### ✅ Path A: Move to LIVE Mode (Binance TH)

**Choose this if:**
- ✅ Paper results are positive (profitable or capital preserved)
- ✅ Downtrend protection worked as expected
- ✅ Win rate is acceptable (>50%)
- ✅ You're comfortable with spot-only trading
- ✅ You prefer simplicity

**Next Steps:**
1. Start with small capital (10-20% of intended amount)
2. Enable LIVE mode in dashboard
3. Monitor closely for first week
4. Scale up gradually if successful

### 🔄 Path B: Migrate to OKX/Other Exchange

**Choose this if:**
- ✅ Paper results validated the system works
- ✅ You want futures/margin trading (profit from downtrends)
- ✅ Lower fees are important (high volume)
- ✅ Want access to more trading pairs
- ✅ Ready for increased complexity

**Why Migrate:**

| Feature | Binance TH (Spot) | OKX/Binance Global (Futures) |
|---------|-------------------|------------------------------|
| **Uptrend Profit** | ✅ BUY → SELL | ✅ LONG position |
| **Downtrend Profit** | ❌ Can only preserve capital | ✅ SHORT position |
| **Potential Returns** | Single direction | Both directions |
| **Risk** | Lower (spot only) | Higher (leverage) |
| **Complexity** | Simple | More complex |

**Migration Effort:**
- Easy: 1-2 hours for spot trading
- Medium: 1-2 days to add futures/shorting logic

### 🔧 Path C: Tune & Retest

**Choose this if:**
- ⚠️ Results are mixed (some good, some bad)
- ⚠️ System behavior is inconsistent
- ⚠️ You're unsure about settings
- ⚠️ Market conditions were unusual (all uptrend or all downtrend)

**Next Steps:**
1. Review the red flags section
2. Adjust configuration based on findings
3. Test for another 7 days
4. Re-evaluate

### ❌ Path D: Disable & Investigate

**Choose this if:**
- ❌ Paper balance significantly down
- ❌ Protection not working (buying into downtrends)
- ❌ Win rate worse than before
- ❌ System bugs or errors

**Next Steps:**
1. Disable downtrend protection
2. Review logs for errors
3. Report issues for investigation
4. Return to baseline trading

---

## 🚀 Exchange Migration Guide

### If You Choose OKX

**Advantages:**
- ✅ Futures/Margin support (short during downtrends)
- ✅ Lower fees (0.08% vs 0.1%)
- ✅ Better API reliability
- ✅ More trading pairs
- ✅ Global access

**Code Changes Required:**

**Easy Changes (Spot Trading Only):**
```python
# In src/roles/job_price.py, line 22
def __init__(self, exchange_id='okx'):  # Change from 'binance'
    # Remove Binance TH workarounds (lines 57-95)
    # Use standard CCXT initialization:
    self.exchange = ccxt.okx({
        'apiKey': self.api_key,
        'secret': self.secret,
        'options': {'defaultType': 'spot'}
    })
```

**Medium Changes (Add Futures):**
- Implement SHORT position logic in Judge
- Add futures balance checking
- Update SniperExecutor for futures orders
- Add leverage management
- Implement liquidation protection

**Estimated Time:**
- Spot migration: 1-2 hours
- Futures implementation: 1-2 days

### Other Exchange Options

| Exchange | Pros | Cons | Recommendation |
|----------|------|------|----------------|
| **OKX** | Best fees, great API | Learning curve | Best overall |
| **Bybit** | Crypto-focused, low fees | Fewer fiat options | Good for crypto-native |
| **Binance Global** | Familiar, most pairs | Regional restrictions | If available in your region |
| **Gate.io** | Many altcoins | Higher fees | For exotic pairs |
| **Kraken** | Very secure, regulated | Higher fees | For security priority |

---

## 💡 Tips for Success

### Do's ✅

1. **Be Patient**
   - Let the full 7 days run
   - Don't panic over 1-2 bad trades
   - Focus on overall trend

2. **Take Notes**
   - Document unusual events
   - Record your observations
   - Note market conditions

3. **Monitor Daily**
   - 5-10 minutes morning/evening
   - Consistency is key
   - Catch issues early

4. **Trust the System**
   - If protection rejects, there's a reason
   - Review the judge_reason in logs
   - Learn from rejected signals

5. **Compare to Reality**
   - Check if rejected trades would have lost money
   - Validate the AI reasoning
   - Confirm trend detection accuracy

### Don'ts ❌

1. **Don't Change Settings Mid-Test**
   - Unless there's a clear bug
   - Changing invalidates the test
   - Wait for week-end review

2. **Don't Disable Protection During Downtrends**
   - That's when you need it most
   - Trust the process
   - Measure the avoided losses

3. **Don't Expect Perfection**
   - Some rejections will be "wrong" (would have won)
   - Focus on net benefit
   - Conservative by design

4. **Don't Compare to Bull Market**
   - Protection shines during downtrends
   - May trade less in mixed markets
   - Quality over quantity

5. **Don't Rush to Live**
   - Paper test thoroughly first
   - Understand the behavior
   - Build confidence in system

---

## 📞 Support & Questions

### When You Return (After 7 Days)

Come back with your tracking data and we can:

1. **Analyze Your Results**
   - Review metrics together
   - Identify patterns
   - Validate effectiveness

2. **Optimize Settings**
   - Fine-tune based on your findings
   - Adjust for your risk tolerance
   - Customize protection mode

3. **Plan Next Steps**
   - Move to LIVE mode
   - Migrate to OKX
   - Add new features
   - Or continue testing

4. **Implement Enhancements**
   - Add futures trading (if migrating)
   - Improve detection algorithm
   - Add more protection modes
   - Whatever you need

### Quick Help During Testing

If you encounter issues during the 7 days:
- Check the logs first
- Review this guide's troubleshooting section
- Run the diagnostic commands
- Document the issue for later review

---

## 🎯 Success Criteria

After 7 days, consider the test **SUCCESSFUL** if:

✅ **Primary Goals:**
- [ ] Paper balance is positive or preserved (not down >5%)
- [ ] Downtrend protection activated during actual downtrends
- [ ] Capital was preserved when BTC dropped
- [ ] Win rate is >50%

✅ **Secondary Goals:**
- [ ] Fewer losing trades than before protection
- [ ] Max drawdown reduced compared to baseline
- [ ] System operated reliably without errors
- [ ] You understand how the protection works

✅ **Bonus Points:**
- [ ] Profited during the test period
- [ ] Avoided significant losses during downtrends
- [ ] Found good settings for your risk tolerance
- [ ] Feel confident to move to live trading

---

## 📚 Appendix: Quick Reference

### Essential Commands Summary

```bash
# Check balance
python3 -c "from src.database import get_db; db = get_db(); print(db.table('simulation_portfolio').select('balance').eq('id', 1).execute().data)"

# Count trades
python3 -c "from src.database import get_db; from datetime import datetime, timedelta; db = get_db(); week_ago = (datetime.now() - timedelta(days=7)).isoformat(); print(len(db.table('trade_signals').select('id').gte('created_at', week_ago).execute().data))"

# Check win rate
python3 -c "from src.database import get_db; db = get_db(); positions = db.table('positions').select('pnl').eq('is_open', False).execute().data; wins = len([p for p in positions if p.get('pnl', 0) > 0]); print(f'{wins}/{len(positions)} = {wins/len(positions)*100:.1f}%' if positions else 'No trades yet')"

# View rejections
python3 -c "from src.database import get_db; db = get_db(); rejected = db.table('trade_signals').select('judge_reason').eq('status', 'REJECTED').order('created_at', desc=True).limit(5).execute().data; [print(r['judge_reason']) for r in rejected]"
```

### Config Quick Changes

```sql
-- Enable/Disable protection
UPDATE bot_config SET value = 'true' WHERE key = 'ENABLE_DOWNTREND_PROTECTION';
UPDATE bot_config SET value = 'false' WHERE key = 'ENABLE_DOWNTREND_PROTECTION';

-- Change mode
UPDATE bot_config SET value = 'STRICT' WHERE key = 'DOWNTREND_PROTECTION_MODE';
UPDATE bot_config SET value = 'MODERATE' WHERE key = 'DOWNTREND_PROTECTION_MODE';
UPDATE bot_config SET value = 'SELECTIVE' WHERE key = 'DOWNTREND_PROTECTION_MODE';

-- Adjust thresholds
UPDATE bot_config SET value = '30' WHERE key = 'DOWNTREND_AI_BOOST';
UPDATE bot_config SET value = '40' WHERE key = 'DOWNTREND_SIZE_REDUCTION_PCT';
UPDATE bot_config SET value = '30' WHERE key = 'ADX_TREND_THRESHOLD';
```

---

**Good luck with your 7-day test! 🚀**

**Remember:** Not losing money IS making money in trading. Capital preservation is profit.

---

**Document Version:** 1.0
**Created:** 2025-01-29
**Next Review:** After your 7-day test period
