# FPL Optimizer - Testing Guide

**Last Updated:** January 13, 2026

This guide explains how to test and validate the FPL optimizer after the Phase 1 & 2 improvements.

---

## 🚀 Quick Start: Test All Features

The fastest way to verify everything is working:

```bash
# Run comprehensive functionality test
python test_optimizer.py
```

This script tests:
- ✓ API client connectivity
- ✓ Data fetching and parsing
- ✓ Advanced predictions (rotation, xG, BPS, confidence)
- ✓ Squad optimization
- ✓ Chip strategy (with GW20 reset support)

**Expected Runtime:** ~30 seconds

---

## 📊 Backtesting: Why It's Challenging

### The FPL API Limitation

The official FPL API **only provides current season data**. Historical seasons are not accessible via the API.

This means:
- ❌ Cannot fetch 2023/24 season data directly
- ❌ Cannot fetch completed 2024/25 gameweeks after season end
- ✅ CAN fetch current 2024/25 gameweeks that have been played

### Backtest Error You Encountered

```
Total Predicted Points: 0.0
Total Actual Points: 0.0
ZeroDivisionError: float division by zero
```

**Root Cause:** The backtest script tried to fetch 2024-25 historical data, but:
1. Either the season hasn't started yet in the API
2. Or the specific gameweeks don't have data available
3. The historical data collector returned empty results

**Fix Applied:** The script now handles this gracefully and provides helpful guidance.

---

## ✅ How to Properly Test

### Option 1: Live Testing (Recommended)

Use the optimizer on your actual team during the current season:

```bash
# Get team recommendations (replace with your team ID)
python -m src.main --mode advanced --team-id YOUR_TEAM_ID

# Long-term planning mode (plans 10 GWs ahead)
python -m src.main --mode advanced --long-term --team-id YOUR_TEAM_ID

# With real xG data (slower but more accurate)
python -m src.main --mode advanced --long-term --use-understat --team-id YOUR_TEAM_ID
```

**Benefits:**
- Tests against real, current data
- Validates API connectivity
- Can compare recommendations week-by-week vs actual outcomes

### Option 2: Current Season Backtesting

If the current season (2024-25) has played gameweeks, you can backtest those:

```bash
# Backtest GW1-10 of current season (if available)
python backtest_phase1.py --season 2024-25 --start-gw 1 --end-gw 10 --collect
```

**Note:** This only works if:
- Current season is 2024-25
- Gameweeks 1-10 have been completed
- The API provides historical GW data for the current season

### Option 3: Manual Validation

Compare optimizer predictions vs actual results manually:

1. **Run optimizer before a gameweek:**
   ```bash
   python -m src.main --mode advanced --team-id YOUR_ID > predictions_gw22.txt
   ```

2. **After the gameweek completes, compare:**
   - Predicted points vs actual points
   - Transfer recommendations vs optimal transfers in hindsight
   - Chip timing suggestions vs actual outcomes

3. **Track over multiple weeks:**
   - Maintain a spreadsheet of predictions vs actuals
   - Calculate Mean Absolute Error (MAE)
   - Measure rank improvement over time

---

## 📈 Validation Metrics

### Prediction Accuracy

**Target:** MAE < 2.5 points per player per gameweek

Calculate manually:
```
MAE = Σ|predicted - actual| / (num_players × num_gameweeks)
```

**Example:**
- Predicted 15 players to score: 60 pts total
- Actual 15 players scored: 65 pts total
- Error: 5 pts / 15 players = 0.33 pts per player ✓ (excellent)

### Transfer Quality

**Target:** Value per transfer > 4.0 points

Track each transfer:
```
Transfer Value = (Player_in points - Player_out points) - transfer_cost
```

If value > 4.0, the transfer was worth taking a hit for.

### Chip Timing

Compare optimizer suggestions vs community consensus:
- **Wildcard:** Should suggest before double gameweeks or after blank GWs
- **Bench Boost:** Should target double gameweeks with strong bench
- **Triple Captain:** Should target premium players in double gameweeks
- **Free Hit:** Should target blank gameweeks

### Long-Term Strategy

Does the optimizer:
- ✓ Plan beyond next gameweek?
- ✓ Coordinate chip timing globally?
- ✓ Identify fixture swings 3-5 GWs ahead?
- ✓ Avoid short-term punts that hurt long-term?

---

## 🧪 Component-Level Testing

### Test Predictions

```python
from src.data.api_client import FPLAPIClient
from src.data.models import build_gameweek_data
from src.prediction.advanced_forecaster import AdvancedForecaster

api_client = FPLAPIClient()
bootstrap = api_client.get_bootstrap_static()
fixtures = api_client.get_fixtures()
gameweek_data = build_gameweek_data(bootstrap, fixtures)

forecaster = AdvancedForecaster(
    gameweek_data,
    api_client,
    use_bonus_model=True,
    use_confidence_model=True
)

# Get predictions for a player
player = gameweek_data.players[0]
prediction = forecaster.predict_points(player, num_gameweeks=3, detailed=True)

print(f"Total: {prediction['total']}")
print(f"Expected Bonus: {prediction['expected_bonus']}")

# Get with confidence
risk_adjusted, distribution = forecaster.predict_with_confidence(
    player, num_gameweeks=3, risk_tolerance='balanced'
)
print(f"Mean: {distribution.mean}, Std Dev: {distribution.std_dev}")
```

### Test BPS Modeling

```python
from src.prediction.bonus_predictor import BonusPointsPredictor

bps_predictor = BonusPointsPredictor(gameweek_data, api_client)

# Predict bonus for a match
player = gameweek_data.players[0]  # Top player
fixture = gameweek_data.fixtures[0]  # Next match

bps, bonus_pts = bps_predictor.get_expected_bonus_for_player(
    player, fixture,
    predicted_goals=0.8,
    predicted_assists=0.3,
    clean_sheet_prob=0.4,
    minutes_expected=90
)

print(f"Expected BPS: {bps:.1f}")
print(f"Expected Bonus Points: {bonus_pts:.2f}")
```

### Test Transfer Valuation

```python
from src.optimization.transfer_evaluator import TransferEvaluator

evaluator = TransferEvaluator(gameweek_data)

# Mock predictions
player_in_predictions = {22: 8.0, 23: 7.5, 24: 9.0}  # Next 3 GWs
player_out_predictions = {22: 4.0, 23: 3.5, 24: 4.5}

transfer_value = evaluator.evaluate_transfer(
    player_in, player_out,
    player_in_predictions, player_out_predictions,
    current_squad, fixtures_in, fixtures_out,
    transfer_cost=-4,  # Taking a hit
    chip_plan=None,
    horizon_gws=3
)

print(f"Total Value: {transfer_value.total_value:.1f} pts")
print(f"Points Gain: {transfer_value.points_gain:.1f} pts")
print(f"Is Worth Hit: {transfer_value.is_worth_hit()}")
print(f"Payback Period: {transfer_value.payback_gameweeks()} GWs")
```

### Test Chip Strategy (GW20 Reset)

```python
from src.optimization.chip_strategy import ChipStrategyOptimizer

chip_optimizer = ChipStrategyOptimizer(gameweek_data)

recommendations = chip_optimizer.get_chip_strategy(
    current_squad,
    expected_points_by_week,
    available_chips=['wildcard1', 'bboost', '3xc', 'freehit'],
    horizon=10
)

# Print formatted summary
chip_optimizer.print_chip_strategy_summary(recommendations)

# Check for H1 warning
metadata = recommendations.get('_metadata', {})
if 'h1_warning' in metadata:
    print(f"⚠️ {metadata['h1_warning']['message']}")
```

---

## 🔍 Debugging Common Issues

### Issue: "Failed to fetch data from API"

**Causes:**
- Network connectivity issues
- FPL API rate limiting
- API maintenance window

**Solutions:**
1. Check internet connection
2. Wait 1-2 minutes and retry
3. Use cached data if available

### Issue: "No predictions generated"

**Causes:**
- Missing player data
- No upcoming fixtures
- API data structure changed

**Solutions:**
1. Check `gameweek_data.current_gameweek` is valid
2. Verify `gameweek_data.fixtures` has upcoming matches
3. Check FPL API status

### Issue: "Understat API very slow"

**Expected:** First run takes ~2 seconds for bulk fetch, then instant on cache

If taking 10+ minutes:
- Bulk fetch may have failed, falling back to per-player calls
- Check `data/understat_cache/` directory
- Delete cache and retry to force fresh bulk fetch

---

## 📋 Test Checklist

Before deploying to live use:

- [ ] Run `python test_optimizer.py` - all tests pass
- [ ] Test with your actual team ID - recommendations generated
- [ ] Verify predictions are reasonable (3-8 pts per player)
- [ ] Check chip strategy respects GW20 reset
- [ ] Confirm BPS predictions are non-zero for top players
- [ ] Validate long-term mode plans 10 GWs ahead
- [ ] Test with and without Understat (should work both ways)

---

## 🎯 Expected Performance

### Prediction Accuracy Targets

- **Top players (Salah, Haaland, etc.):** Within ±3 points per GW
- **Mid-range players:** Within ±2 points per GW
- **Bench players:** Within ±1 point per GW
- **Overall MAE:** < 2.5 points per player per GW

### Point Improvement vs Baseline

Estimated impact vs basic optimizer:
- **Phase 1 (Long-term + xG):** +90-140 pts/season
- **Phase 2 (BPS + Confidence + Transfers):** +50-80 pts/season
- **Phase 3 (Chip reset):** +5-10 pts/season
- **Total:** +145-230 pts/season

### Rank Improvement

For competent FPL managers:
- Starting rank 500k → Target: Top 100k (feasible)
- Starting rank 200k → Target: Top 50k (achievable)
- Starting rank 100k → Target: Top 20k (with good execution)

---

## 📞 Troubleshooting

If tests fail or unexpected behavior:

1. **Check Python version:** Requires Python 3.8+
2. **Verify dependencies:** `pip install -r requirements.txt`
3. **Clear cache:** Delete `data/` directory and retry
4. **Check logs:** Look for error messages in output
5. **Report issues:** Include full error trace

---

## 🚀 Next Steps

Once testing is complete:

1. **Use for current gameweek:** Get recommendations
2. **Track predictions:** Record for validation
3. **Refine parameters:** Adjust based on observed accuracy
4. **Complete remaining priorities:** Rank projection, ML models

---

**Happy Testing! 🎉**
