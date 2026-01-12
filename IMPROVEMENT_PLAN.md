# FPL Optimizer - Improvement Plan

## Goal
Build the **best FPL optimizer in the world** - practical, high-quality suggestions based on real FPL expertise.

**Current State**: 60/100
**Target**: 95+/100 (world-class)

---

## 🔴 PHASE 1: CRITICAL BUGS (Fix Immediately)

### Issue #1: Transfer Logic Broken - Not Using All Free Transfers
**Problem**: With 5 free transfers, recommends 1 per week for 5 weeks instead of optimizing all 5 for next gameweek.

**Impact**: CRITICAL - wastes valuable free transfers

**Fix**:
- Modify `transfer_optimizer.py` to use `min(free_transfers, 5)` transfers at once
- Update `suggest_transfers()` to accept `num_transfers` parameter matching available free transfers
- Show "You have 5 free transfers. Best 5 transfers for GW22:"

**Files**: `src/optimization/transfer_optimizer.py`, `src/main.py`

---

### Issue #2: Chip Strategy Violates FPL Rules - Multiple Chips Per Week
**Problem**: Recommends Wildcard + Triple Captain for GW22 (FPL allows only 1 chip per gameweek)

**Impact**: CRITICAL - breaks fundamental FPL rule, confuses users

**Fix**:
- Add `resolve_chip_conflicts()` method to `ChipStrategyOptimizer`
- After evaluating all chips:
  1. Group recommendations by gameweek
  2. For GWs with multiple chip options, pick highest value
  3. Show runner-up option for different GW
- Display: "Note: Only one chip allowed per gameweek. Recommended: Wildcard (highest value)"

**Files**: `src/optimization/chip_strategy.py`, `src/main.py`

---

### Issue #3: No Integration Between Components
**Problem**: Transfer recommendations ignore chip decisions (shows transfers even when Wildcard recommended)

**Impact**: CRITICAL - confusing and conflicting recommendations

**Fix**:
- Implement sequential decision flow in `main.py`:
  1. Evaluate chips FIRST
  2. If Wildcard recommended for current GW:
     → Show optimal 15-man squad from scratch (unlimited transfers)
     → Skip regular transfer recommendations
  3. If no Wildcard:
     → Show best N transfers from current squad (N = free_transfers)
- Add "Strategy Scenarios" section showing:
  - **Scenario A**: Use Wildcard in GW22 (show optimal squad)
  - **Scenario B**: Save Wildcard (show best N transfers)

**Files**: `src/main.py`

---

## 🟠 PHASE 2: CORE FPL FUNCTIONALITY (Next Priority)

### Issue #4: Player Selling Value Not Tracked
**Problem**: Optimizer doesn't know what you paid for players, so can't calculate true budget

**Example**: Bought Player A for £10.0m, now £10.4m, sell for £10.2m (£0.2m locked in player value)

**Fix**:
- Add `purchase_price` field to team data
- Calculate `selling_price = purchase_price + (current_price - purchase_price) / 2`
- Show "Liquid bank: £1.8m | Locked in players: £2.5m | Total budget: £4.3m"

**Files**: `src/data/models.py`, `src/data/api_client.py`

---

### Issue #5: No Price Change Prediction
**Problem**: Doesn't warn about impending price drops/rises

**Impact**: Can lose £0.1m-0.3m in team value per week

**Fix**:
- Integrate price change prediction (fplstatistics.com style)
- Flag players: "⚠️ Haaland expected to rise tonight (99% probability)"
- Prioritize transfers for players about to drop

**Files**: `src/prediction/price_predictor.py` (new), `src/main.py`

---

### Issue #6: Fixture Difficulty Too Simplistic
**Problem**: Uses FPL's 1-5 difficulty rating only, doesn't consider detailed stats

**Fix**:
- Enhance fixture analysis with:
  - Team attack strength vs opponent defense (and vice versa)
  - Home/away form splits
  - Recent form (last 5 games)
  - Key injuries/suspensions
- Weight components: 40% base difficulty, 30% team strength, 20% form, 10% injuries

**Files**: `src/prediction/advanced_forecaster.py`

---

### Issue #7: No Expected Goals (xG) Data
**Problem**: Uses actual goals/assists, not underlying stats (xG is better predictor)

**Fix**:
- Integrate xG, xA, xGI data (FBRef/Understat APIs)
- Prediction formula: `base_points = (xG * 5) + (xA * 3) + (clean_sheet_prob * 4)`
- Flag players: "0 goals but 2.5 xG → unlucky, likely to score soon"

**Files**: `src/prediction/xg_predictor.py` (new), `src/prediction/advanced_forecaster.py`

---

### Issue #8: No Rotation Risk Modeling
**Problem**: Doesn't predict minutes based on fixture congestion (Pep Roulette!)

**Fix**:
- Model rotation risk: `minutes_prob = base_minutes * (1 - rotation_risk)`
- Rotation risk factors:
  - Fixtures in next 7 days (more fixtures = higher risk)
  - European games (CL/EL mid-week = rotation)
  - Manager tendency (Pep > Arteta > others)
- Adjust expected points by minutes probability

**Files**: `src/prediction/rotation_predictor.py` (new)

---

## 🟡 PHASE 3: STRATEGIC DEPTH (Medium Priority)

### Issue #9: No Differential Strategy
**Problem**: Doesn't consider ownership % for rank climbing

**Fix**: `value = expected_points * (1 + differential_weight * (1 - ownership/100))`

### Issue #10: No Captaincy Depth
**Fix**: Provide 2-3 captaincy options, consider variance and reliability

### Issue #11: No Bench Strategy (Bench Fodder)
**Fix**: Optimize for strong starting XI + cheap bench, not 15 equal players

### Issue #12: No Template Awareness
**Fix**: Show "11/15 players match top 10k template (73%)"

### Issue #13: No Long-Term Planning
**Fix**: Add "season plan" mode showing GW22-38 strategy

### Issue #14: No Auto-Sub Handling
**Fix**: Consider vice-captain in optimization

### Issue #15: No Bonus Points Modeling
**Fix**: Model bonus based on position, actions (passes, tackles, saves)

---

## 🟢 PHASE 4: POLISH & ENHANCEMENT (Nice-to-Have)

### Issue #16: No Learning/Improvement
**Fix**: Track prediction accuracy, adjust model weights

### Issue #17: No Multi-Objective Optimization
**Fix**: Optimize for points + risk + team value + differentials

### Issue #18: No Interactive Mode
**Fix**: Allow "what if I keep Salah instead?" exploration

### Issue #19: No Visualization
**Fix**: Add fixture calendars, charts, graphs

### Issue #20: No "Why" Explanations
**Fix**: Explain reasoning: "Transfer out X: poor fixtures (GW23-25), low xG (0.3), dropping tonight"

---

## Implementation Timeline

### Immediate (Current Session)
- [x] Document plan
- [x] Fix Issue #1: Use all free transfers
- [x] Fix Issue #2: Chip conflict resolution
- [x] Fix Issue #3: Integrate chips → transfers flow

### Short-term (Next Session)
- [ ] Issue #4: Player selling values
- [ ] Issue #6: Better fixture analysis
- [ ] Issue #11: Bench fodder strategy

### Medium-term (Next Week)
- [ ] Issue #5: Price change predictions
- [ ] Issue #7: xG integration
- [ ] Issue #8: Rotation modeling
- [ ] Issue #12: Template awareness

### Long-term (Next Month)
- [ ] Phase 3 items (strategic depth)
- [ ] Phase 4 items (polish)

---

## Success Metrics

**After Phase 1**: 75/100
- No critical bugs
- Recommendations follow FPL rules
- Clear, non-conflicting advice

**After Phase 2**: 85/100
- FPL expertise baked in
- Better predictions than FPL's own
- Price change awareness

**After Phase 3**: 95/100
- Strategic depth
- Rank-aware recommendations
- Long-term planning

**World-Class**: 98/100
- Proven accuracy through backtesting
- Used and trusted by top managers
- Continuous learning and improvement

---

## Notes
- Focus on **practical, actionable advice**
- Optimize for **real-world FPL decisions**
- Every recommendation must **follow FPL rules**
- Build for **serious FPL managers** who want to climb ranks
