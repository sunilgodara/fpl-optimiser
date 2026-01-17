# Backtesting Guide - Phase 1 Validation

This guide shows you how to validate the Phase 1 improvements (Long-Term Optimizer + Real xG Integration) using historical FPL data.

---

## Quick Start (5 Minutes)

### Step 1: Collect Historical Data

```bash
# Quick test: Collect first 5 gameweeks of current season
python -m src.utils.historical_data --quick

# Full collection: Collect entire season
python -m src.utils.historical_data --season 2024-25 --start-gw 1 --end-gw 20
```

**What this does:**
- Fetches actual player scores from past gameweeks
- Caches data locally in `data/historical/`
- Takes ~2-5 minutes depending on number of gameweeks

### Step 2: Run Backtest

```bash
# Test on first 5 gameweeks
python backtest_phase1.py --season 2024-25 --start-gw 1 --end-gw 5

# With automatic data collection
python backtest_phase1.py --season 2024-25 --start-gw 1 --end-gw 10 --collect
```

**What this does:**
- Simulates optimizer running on historical data
- Compares predicted points vs actual outcomes
- Generates accuracy metrics

### Step 3: View Results

Results are saved to:
```
data/backtest_phase1_2024-25_gw1-5.json
```

---

## Detailed Backtesting Process

### What Gets Tested

1. **Prediction Accuracy**
   - Mean Absolute Error (MAE): How far off predictions are
   - Prediction Bias: Are we over or under-predicting?
   - Target: MAE < 2.5 points per player per GW

2. **Long-Term Optimizer Quality**
   - Transfer sequencing value
   - Chip timing effectiveness
   - Cumulative points vs baseline

3. **xG Integration Impact**
   - Compare xG-based predictions vs ICT-based
   - Identify over/underperformers correctly
   - Value pick detection accuracy

---

## Metrics Explained

### Mean Absolute Error (MAE)

```
MAE = Average |Predicted - Actual| per player per GW
```

**Targets:**
- Excellent: MAE < 2.0
- Good: MAE < 2.5
- Needs improvement: MAE > 3.0

**Example:**
- Predicted Salah would score 8 points
- Salah actually scored 12 points
- Error: |8 - 12| = 4 points

### Prediction Accuracy %

```
Accuracy = (1 - MAE / Average_Actual_Points) × 100%
```

**Targets:**
- Excellent: > 80% accuracy
- Good: > 70% accuracy
- Baseline: ~60% accuracy

### Prediction Bias

```
Bias = Total_Predicted - Total_Actual
```

- **Positive bias**: Over-predicting (optimistic)
- **Negative bias**: Under-predicting (pessimistic)
- **Target**: Close to 0 (unbiased)

---

## Advanced Backtesting

### Test Against Different Strategies

```python
# Compare long-term optimizer vs greedy (next GW only)
python backtest_comparison.py --strategies long-term,greedy --season 2024-25
```

### Test xG Integration Impact

```python
# Compare with vs without real xG
python backtest_xg_impact.py --with-understat --season 2024-25
```

### Test on Multiple Seasons

```bash
# Test on 2023/24 season
python backtest_phase1.py --season 2023-24 --start-gw 1 --end-gw 38

# Test on 2024/25 season
python backtest_phase1.py --season 2024-25 --start-gw 1 --end-gw 20
```

---

## Interpreting Results

### Example Output

```
BACKTEST RESULTS
================================================================================

Gameweeks Tested: 5
Total Predicted Points: 1,450.0
Total Actual Points: 1,380.0
Prediction Bias: +70.0 points (optimistic)
Mean Absolute Error: 2.1 points per player per GW
Prediction Accuracy: 76.3%

✓ Good accuracy (> 70%)
⚠️ Slight optimistic bias (over-predicting by ~5%)
```

### What This Means

- **MAE 2.1**: Predictions are off by ~2 points per player on average (GOOD)
- **76.3% accuracy**: Better than baseline (GOOD)
- **+70 bias**: Slightly over-optimistic, might need calibration
- **Overall**: Phase 1 is working well!

---

## Common Issues

### "No historical data found"

**Solution:**
```bash
python -m src.utils.historical_data --season 2024-25 --start-gw 1 --end-gw 5
```

### "Rate limit exceeded"

**Solution:** The data collector has built-in rate limiting (0.5s delay). If you still hit limits:
```python
# In historical_data.py, increase delay:
time.sleep(1.0)  # Instead of 0.5
```

### "Understat API not available"

**Solution:** Install dependencies:
```bash
pip install understatapi beautifulsoup4 lxml
```

---

## Validation Checklist

Use this checklist to validate Phase 1:

- [ ] Collect historical data for at least 5 gameweeks
- [ ] Run backtest with baseline strategy
- [ ] Check MAE < 2.5 points per player
- [ ] Check prediction accuracy > 70%
- [ ] Compare long-term optimizer vs greedy approach
- [ ] Test xG integration impact
- [ ] Validate chip timing recommendations
- [ ] Review transfer sequencing quality

---

## Next Steps

### If Backtest Passes (MAE < 2.5, Accuracy > 70%)

✅ **Phase 1 validated!** Proceed to Phase 2:
1. Implement BPS modeling
2. Add prediction confidence intervals
3. Enhance transfer valuation

### If Backtest Needs Improvement

⚠️ **Tune hyperparameters:**
1. Adjust form weight (currently 35%)
2. Adjust fixture weight (currently 25%)
3. Calibrate xG integration weight
4. Re-run backtest to measure improvement

---

## Automated Testing

### Run Full Test Suite

```bash
# Run all backtests automatically
./run_all_backtests.sh
```

This will:
1. Collect data for 2023/24 and 2024/25 seasons
2. Run Phase 1 backtest
3. Compare strategies
4. Generate report with all metrics
5. Save results to `data/backtest_reports/`

---

## Manual Verification

### Compare Against Community Benchmarks

1. **FPL Review Average**
   - Target: MAE ~2.3 points (industry benchmark)

2. **Top 10k Template**
   - Target: Match or beat top 10k average decisions

3. **Historical Champions**
   - Target: Would optimizer decisions lead to top 10k finish?

### Spot Check Specific Gameweeks

```python
# Check optimizer decisions for a specific past gameweek
python spot_check.py --season 2024-25 --gameweek 15

# This shows:
# - What transfers optimizer recommended
# - What actual top managers did
# - Points differential
```

---

## Debugging Poor Results

### If MAE > 3.0 (Poor Accuracy)

**Possible issues:**
1. Not using real xG data → Check Understat connection
2. Form weight too high → Reduce from 35% to 30%
3. Fixture model inaccurate → Review fixture difficulty adjustments

**Debug steps:**
```bash
# Test with ICT-only (no Understat)
python backtest_phase1.py --no-understat

# Compare results to identify if xG integration is issue
```

### If Bias > ±100 (Highly Biased)

**Over-predicting (+bias):**
- Reduce optimistic adjustments in forecaster
- Lower rotation risk adjustments
- Calibrate xG multipliers downward

**Under-predicting (-bias):**
- Increase expected points slightly
- Review if missing bonus points
- Check fixture multipliers aren't too conservative

---

## Data Sources

### FPL Official API
- Player scores: `https://fantasy.premierleague.com/api/`
- Free, no API key needed
- Rate limit: ~10 requests/minute

### Understat (xG Data)
- Real xG/xA: `https://understat.com/`
- Via `understatapi` Python library
- Rate limit: ~1 request/second

### Historical Archives
- Past seasons: `https://github.com/vaastav/Fantasy-Premier-League`
- Community-maintained
- CSV format

---

## Performance Targets

### Phase 1 Success Criteria

| Metric | Baseline | Target | Stretch Goal |
|--------|----------|--------|--------------|
| MAE | 3.0 pts | < 2.5 pts | < 2.0 pts |
| Accuracy | 60% | > 70% | > 80% |
| Transfer Value | +3 pts/transfer | +4 pts/transfer | +5 pts/transfer |
| Chip Timing | Random | Top 50% | Top 25% |

### Comparison Benchmarks

**vs Simple Optimizer (greedy next GW):**
- Target: +50-100 points over season (Phase 1 advantage)

**vs FPL Review:**
- Target: Within ±50 points (competitive with industry leader)

**vs Top 10k Average:**
- Target: Match or beat (validates optimizer quality)

---

## Resources

### Documentation
- `FPL_OPTIMIZER_ASSESSMENT.md` - Full improvement plan
- `IMPLEMENTATION_PROGRESS.md` - What's been implemented
- `README.md` - Project overview

### Code
- `src/utils/backtesting.py` - Backtesting framework
- `src/utils/historical_data.py` - Data collector
- `backtest_phase1.py` - Phase 1 validation script

### Community
- FPL Subreddit: r/FantasyPL
- FPL Discord: Discussion and strategies
- FPL Review: Industry benchmark tool

---

## FAQ

**Q: How much historical data do I need?**
A: Minimum 5 gameweeks for testing, 20+ for reliable validation.

**Q: Can I backtest current season?**
A: Yes, but only completed gameweeks (use data that's already happened).

**Q: How long does backtesting take?**
A: ~5-10 minutes for data collection, ~1-2 minutes for backtest.

**Q: Will backtest results match live performance?**
A: Similar but not identical - live has uncertainty that backtest doesn't.

**Q: What if I can't access Understat?**
A: Optimizer automatically falls back to ICT proxy (slightly less accurate).

---

**Ready to backtest? Run:**
```bash
python backtest_phase1.py --season 2024-25 --start-gw 1 --end-gw 5 --collect
```
