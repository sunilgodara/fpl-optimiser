# Prediction Engine Improvement Plan

## Current State (v1.0)

### Performance Metrics
- **Average Points/GW**: 57.6 (Target: 60-70 for world-class)
- **Elite Player Accuracy**: Mixed
  - Haaland: 5.13 pts/GW (actual ~6-7) - **85% accurate** ✅
  - Salah: 1.81 pts/GW (actual ~6.5) - **28% accurate** ❌
  - Palmer: 2.02 pts/GW (actual ~5.5) - **37% accurate** ❌
  - Saka: 3.51 pts/GW (actual ~5.5) - **64% accurate** ⚠️

### Known Issues
1. **Player History API Failures**
   - Some players (Salah) have Form=0.0 due to recent absences (AFCON)
   - Fallbacks are now in place but could be smarter

2. **Base Prediction Too Conservative**
   - Formula: `0.60 × form + 0.40 × PPG`
   - PPG averages over full season (including early season struggles)
   - Recent form should have more weight for in-form players

3. **Rotation Model Disabled**
   - Was giving 58.8% rotation risk for Haaland (guaranteed starter!)
   - Needs complete rework with better training data

4. **xG Model Disabled**
   - Disabled for speed
   - Could add 10-15% prediction accuracy when working correctly

5. **Fixture Difficulty Not Differentiated Enough**
   - Multipliers: Easy (1.35x) vs Hard (0.65x) = 2x spread
   - Real-world variance is higher (some players 3-4x better in easy fixtures)

---

## Improvement Roadmap

### Phase 1: Quick Wins (1-2 hours)
**Goal**: Improve predictions to 60+ pts/GW average

#### 1.1 Smarter Form Handling for Returning Players
**Problem**: Salah gets Form=0.0 due to AFCON absence

**Solution**:
```python
def calculate_form_score(self, player: Player) -> float:
    """Enhanced form calculation with smart fallbacks."""
    history = self._get_player_history(player)

    if not history or 'history' not in history:
        # Check if player was recently absent (AFCON, injury)
        if player.price >= 10.0 and player.form < 1.0:
            # Use PPG as proxy for expected form
            return player.points_per_game
        return float(player.form) if player.form > 0 else 2.0

    # Filter out games with 0 minutes (suspended, international duty)
    recent_games = [g for g in history['history'][-8:] if g['minutes'] > 0]

    if len(recent_games) == 0:
        # No recent games - use PPG or price-based estimate
        return player.points_per_game if player.points_per_game > 0 else (player.price * 0.4)

    # Take last 5 games where they actually played
    recent_games = recent_games[-5:]
    # ... rest of exponential weighted average logic
```

**Expected Impact**: Salah 1.81 → 3.5-4.5 pts/GW

---

#### 1.2 Dynamic Form/PPG Weighting
**Problem**: Formula uses fixed 60/40 split, but should favor form for in-form players

**Solution**:
```python
def calculate_base_prediction(self, player: Player, form_score: float, ppg: float) -> float:
    """Dynamic weighting based on player state."""

    # If player is hot (form >> PPG), trust form more
    if form_score > ppg * 1.3:
        form_weight = 0.75
        ppg_weight = 0.25
    # If player is cold (form << PPG), trust PPG more (likely returning to mean)
    elif form_score < ppg * 0.7:
        form_weight = 0.40
        ppg_weight = 0.60
    # Otherwise use standard weights
    else:
        form_weight = 0.60
        ppg_weight = 0.40

    return form_weight * form_score + ppg_weight * ppg
```

**Expected Impact**: +2-3% accuracy for hot/cold players

---

#### 1.3 Position-Specific Prediction Floors
**Problem**: Premium forwards/midfielders get penalized too much by consistency/minutes

**Solution**:
```python
def predict_points(self, player: Player, num_gameweeks: int = 1) -> float:
    # ... existing calculation logic ...

    # Ensure minimum expected points for premium players
    POSITION_PRICE_FLOORS = {
        'FWD': {15.0: 5.0, 12.0: 4.0, 10.0: 3.5},  # price: min_pts/GW
        'MID': {13.0: 5.5, 10.0: 4.0, 8.0: 3.0},
        'DEF': {7.0: 4.0, 6.0: 3.0, 5.0: 2.5},
        'GK': {5.5: 3.5, 5.0: 3.0, 4.5: 2.5}
    }

    position_floors = POSITION_PRICE_FLOORS.get(player.position, {})
    for price_threshold, min_pts in sorted(position_floors.items(), reverse=True):
        if player.price >= price_threshold:
            total_prediction = max(total_prediction, min_pts * num_gameweeks)
            break

    return total_prediction
```

**Expected Impact**: Palmer 2.02 → 3.0 pts/GW, Saka 3.51 → 4.0 pts/GW

---

### Phase 2: Model Improvements (4-6 hours)
**Goal**: Reach 62-65 pts/GW average with better underlying models

#### 2.1 Rebuild Rotation Risk Model
**Current Problem**: Gives 58.8% rotation risk to Haaland!

**Root Cause Analysis**:
- Model likely based on historical rotation patterns
- Doesn't account for player importance/price
- No squad depth analysis

**New Approach**:
```python
class RotationPredictor:
    def calculate_rotation_risk(self, player: Player, gameweek: int) -> float:
        """
        Improved rotation risk using multiple signals.

        Risk Factors:
        1. Fixture congestion (UCL, FA Cup, etc.)
        2. Squad depth at position
        3. Recent minutes (fatigue indicator)
        4. Player importance (price, ownership, PPG)
        """

        # Premium players (£10m+) are rarely rotated
        if player.price >= 10.0:
            base_risk = 0.05  # Max 5% for elite players
        elif player.price >= 8.0:
            base_risk = 0.15  # 15% for premium
        else:
            base_risk = 0.30  # 30% for budget

        # Check fixture congestion (DGW/BGW analysis)
        fixtures_this_week = self._count_fixtures_for_team(player.team_id, gameweek)
        if fixtures_this_week == 2:  # Double gameweek
            base_risk += 0.20  # Higher rotation risk

        # Check recent minutes (fatigue)
        recent_minutes = self._get_recent_minutes(player, num_games=3)
        if recent_minutes >= 270:  # 3x 90min
            base_risk += 0.10

        # Cap at reasonable maximum
        return min(base_risk, 0.40)
```

**Expected Impact**: Haaland rotation risk 58.8% → 5-10%

---

#### 2.2 Re-enable xG Model with Fixes
**Why Disabled**: Added complexity without clear benefit

**Improvements Needed**:
- Better xG/xA data source (Understat is slow)
- Position-specific xG → points conversion
- Combine with historical overperformance/underperformance

**Implementation**:
```python
class XGIntegrator:
    # Position-specific conversion rates (xG/xA to FPL points)
    XG_CONVERSION = {
        'FWD': {'xG': 5.0, 'xA': 3.5},   # Goals worth more for forwards
        'MID': {'xG': 5.5, 'xA': 3.5},   # Goals + assists equally valuable
        'DEF': {'xG': 6.5, 'xA': 3.5},   # Goals worth even more for defenders
        'GK': {'xG': 0.0, 'xA': 0.0}     # Goalkeepers don't score/assist
    }

    def adjust_prediction_for_xg(self, player: Player, base_prediction: float) -> float:
        """Adjust prediction using xG/xA data."""
        xg_data = self._get_player_xg(player)

        if not xg_data:
            return base_prediction

        # Calculate expected FPL points from xG/xA
        conversion = self.XG_CONVERSION[player.position]
        xg_expected_pts = (
            xg_data['xG'] * conversion['xG'] +
            xg_data['xA'] * conversion['xA']
        )

        # Blend with base prediction (70% base, 30% xG)
        return 0.70 * base_prediction + 0.30 * xg_expected_pts
```

---

#### 2.3 Fixture Difficulty Recalibration
**Problem**: Multipliers too conservative (1.35x easy, 0.65x hard)

**Solution**:
```python
# Recalibrated difficulty multipliers
DIFFICULTY_MULTIPLIERS = {
    1: 1.55,  # Very easy (was 1.35)
    2: 1.25,  # Easy (was 1.18)
    3: 1.00,  # Average (unchanged)
    4: 0.75,  # Hard (was 0.82)
    5: 0.55,  # Very hard (was 0.65)
}

# Position-specific fixture sensitivity
POSITION_FIXTURE_SENSITIVITY = {
    'FWD': 1.2,  # Forwards most affected by fixtures
    'MID': 1.0,  # Midfielders average
    'DEF': 0.8,  # Defenders less affected (clean sheets vs any opponent)
    'GK': 0.7    # Goalkeepers least affected
}
```

**Expected Impact**: Better differentiation between easy/hard runs

---

### Phase 3: Advanced Features (8-12 hours)
**Goal**: Reach 65-70 pts/GW with ML-based predictions

#### 3.1 Historical Performance Database
**Purpose**: Track actual vs predicted performance to improve model

**Schema**:
```python
class PredictionTracker:
    """Track predictions vs actuals for model improvement."""

    def __init__(self):
        self.db = {
            'predictions': [],  # List of (player_id, gw, predicted_pts, actual_pts)
            'model_accuracy': {},  # Accuracy by player/position/price_bracket
        }

    def track_prediction(self, player_id: int, gameweek: int,
                        predicted: float, actual: float):
        """Record prediction and actual result."""
        error = abs(predicted - actual)
        self.db['predictions'].append({
            'player_id': player_id,
            'gameweek': gameweek,
            'predicted': predicted,
            'actual': actual,
            'error': error
        })

    def get_player_bias(self, player_id: int) -> float:
        """Get systematic over/under prediction for player."""
        player_preds = [p for p in self.db['predictions']
                       if p['player_id'] == player_id]

        if len(player_preds) < 3:
            return 0.0

        # Calculate average prediction error
        avg_predicted = statistics.mean([p['predicted'] for p in player_preds])
        avg_actual = statistics.mean([p['actual'] for p in player_preds])

        return avg_actual - avg_predicted  # Positive = we underpredict
```

---

#### 3.2 Machine Learning Model (Optional)
**Purpose**: Learn complex patterns from historical data

**Approach**: Gradient Boosting (XGBoost/LightGBM)

**Features**:
- Player stats: PPG, form, minutes, price
- Team stats: Team form, strength ratings
- Fixture: Opponent strength, home/away, fixture difficulty
- Historical: Last 5 games performance
- Opponent-specific: Performance vs top 6, vs bottom 6

**Training**:
```python
import xgboost as xgb

class MLPredictor:
    def __init__(self):
        self.model = xgb.XGBRegressor(
            objective='reg:squarederror',
            n_estimators=100,
            max_depth=6,
            learning_rate=0.1
        )

    def train(self, historical_data):
        """Train on past seasons."""
        X = self._extract_features(historical_data)
        y = historical_data['actual_points']

        self.model.fit(X, y)

    def predict(self, player: Player, fixture: Fixture) -> float:
        """Predict points for player in fixture."""
        features = self._extract_features_for_player(player, fixture)
        return self.model.predict([features])[0]
```

**Expected Impact**: +5-10% accuracy, 65-70 pts/GW average

---

## Testing & Validation

### Backtesting Framework
```python
class PredictionBacktest:
    """Backtest prediction engine on historical data."""

    def run_backtest(self, seasons: List[str]) -> Dict:
        """
        Test predictions against historical gameweeks.

        Returns:
            {
                'mae': float,  # Mean absolute error
                'rmse': float,  # Root mean squared error
                'accuracy_by_position': Dict[str, float],
                'accuracy_by_price_bracket': Dict[str, float]
            }
        """
        pass
```

### Key Metrics to Track
1. **Mean Absolute Error (MAE)**: Average prediction error in pts/GW
   - Target: < 1.5 pts/GW for elite players
2. **Squad Expected Points**: Average predicted pts/GW for optimal squad
   - Target: 65-70 pts/GW
3. **Correlation**: Predicted rank vs actual rank
   - Target: > 0.7 Spearman correlation

---

## Priority Order

### Immediate (Do First)
1. ✅ **Phase 1.1**: Smarter form handling for returning players
   - Impact: High (fixes Salah, Palmer)
   - Effort: Low (1 hour)

2. ✅ **Phase 1.3**: Position-specific prediction floors
   - Impact: Medium (improves premium players)
   - Effort: Low (30 min)

### Short-term (This Week)
3. **Phase 2.1**: Rebuild rotation risk model
   - Impact: High (currently disabled due to bugs)
   - Effort: Medium (3-4 hours)

4. **Phase 1.2**: Dynamic form/PPG weighting
   - Impact: Medium (better hot/cold player handling)
   - Effort: Low (1 hour)

### Medium-term (Next Sprint)
5. **Phase 2.3**: Fixture difficulty recalibration
   - Impact: Medium (better fixture run identification)
   - Effort: Medium (2-3 hours)

6. **Phase 2.2**: Re-enable xG model
   - Impact: Medium-High (adds another signal)
   - Effort: High (4-6 hours with testing)

### Long-term (Future)
7. **Phase 3.1**: Historical performance tracking
   - Impact: High (enables continuous improvement)
   - Effort: High (8+ hours)

8. **Phase 3.2**: ML-based predictions (Optional)
   - Impact: Very High (could reach 65-70 pts/GW)
   - Effort: Very High (12+ hours + data collection)

---

## Success Criteria

### Minimum Viable (v1.1)
- ✅ Average squad expected points: 57+ pts/GW
- ✅ Haaland prediction within 20% of actual
- ⚠️ Salah prediction within 50% of actual (currently 28%)
- ✅ No obviously broken predictions (negative, > 20 pts/GW)

### Good (v1.5)
- Average squad expected points: 60+ pts/GW
- Elite players within 20% of actual
- All players within 50% of actual
- Rotation risk model functional

### Excellent (v2.0)
- Average squad expected points: 65+ pts/GW
- Elite players within 10% of actual
- Most players within 30% of actual
- ML model integration
- Backtesting framework operational

---

## Technical Debt to Address

1. **Player History API Caching**: Currently fetches every time, should cache
2. **Error Handling**: Fails silently on API errors, needs better logging
3. **Unit Tests**: Prediction engine has no unit tests
4. **Documentation**: Prediction formula not documented
5. **Configuration**: Hard-coded weights should be in config file

---

## References & Resources

### FPL Data Sources
- Official FPL API: `https://fantasy.premierleague.com/api/`
- Understat (xG data): `https://understat.com/`
- FBref (advanced stats): `https://fbref.com/`

### Similar Projects
- **FPL Review**: https://fplreview.com/ (ML-based predictions)
- **FiveThirtyEight**: Uses xG + team ratings
- **FPL Analytics**: Community-driven prediction models

### Research Papers
- "Predicting Football Results Using Machine Learning Techniques" (2019)
- "Expected Goals: A Primer" - StatsBomb
- "Fantasy Football Optimization" - OR Practitioner Papers

---

**Last Updated**: 2026-01-17
**Current Version**: v1.0
**Target Version**: v1.1 (by 2026-01-24)
