# FPL Optimizer

A comprehensive Fantasy Premier League squad optimizer that maximizes expected points using advanced predictions, multi-week transfer planning, and chip strategy optimization.

## Features

### Core Functionality
- **FPL API Integration**: Fetch live player data, fixtures, and team information from official FPL API
- **Advanced Predictions**: Multi-factor prediction engine using:
  - Historical performance data
  - Form analysis with exponential weighting
  - Fixture difficulty with position-specific adjustments
  - Minutes reliability and consistency metrics
  - Team strength analysis (home/away splits)
- **Squad Optimization**: Linear programming-based optimizer (PuLP) respecting all FPL constraints
- **Starting XI & Captain**: Optimal lineup selection with valid formations

### Advanced Features
- **Transfer Planning**: Multi-week transfer optimization with -4 point penalty consideration
- **Chip Strategy**: Intelligent timing for all chips:
  - **Wildcard**: Identifies best gameweeks based on fixture swings and squad health
  - **Bench Boost**: Targets double gameweeks with strong bench
  - **Triple Captain**: Finds optimal captain in double/easy gameweeks
  - **Free Hit**: Identifies blank gameweeks and one-week opportunities
- **Multi-Week Horizon**: Plan 5-10 gameweeks ahead
- **Backtesting Framework**: Test strategies on historical data
- **Strategy Presets**: Conservative, Balanced, and Aggressive configurations

## Installation

```bash
pip install -r requirements.txt
```

## Usage

### Basic Mode (Quick Squad Optimization)

```bash
# Generate optimal squad from scratch
python -m src.main

# With balanced strategy preset (default)
python -m src.main --preset balanced

# Conservative approach (fewer transfers, lower risk)
python -m src.main --preset conservative

# Aggressive approach (more transfers, differential picks)
python -m src.main --preset aggressive
```

### Advanced Mode (Full Strategy Planning)

```bash
# Run advanced mode with transfer planning and chip strategy
python -m src.main --mode advanced

# With your FPL team ID (future: fetch your current squad)
python -m src.main --mode advanced --team-id 450211

# Advanced mode with aggressive strategy
python -m src.main --mode advanced --preset aggressive
```

## Command-Line Options

- `--mode`: `basic` or `advanced` (default: `basic`)
- `--preset`: `conservative`, `balanced`, or `aggressive` (default: `balanced`)
- `--team-id`: Your FPL team ID for fetching current squad (optional)

## Output Examples

### Basic Mode
- Top predicted players by position
- Optimal 15-player squad (within budget)
- Best starting XI with formation
- Captain selection
- Expected points breakdown

### Advanced Mode
All of the above, plus:
- **Transfer Recommendations**: Top 5 transfers with reasoning
- **Multi-Week Transfer Plan**: 5-week rolling plan
- **Chip Strategy**: When to use each chip for maximum value
- **Double Gameweek Detection**: Automatic identification
- **Blank Gameweek Warnings**: Teams not playing

## Project Structure

```
src/
├── data/
│   ├── api_client.py          # FPL API wrapper
│   └── models.py               # Data models (Player, Team, Fixture)
├── prediction/
│   ├── forecaster.py           # Basic prediction engine
│   └── advanced_forecaster.py  # Advanced multi-factor predictions
├── optimization/
│   ├── squad_optimizer.py      # LP-based squad selection
│   ├── transfer_optimizer.py   # Multi-week transfer planning
│   └── chip_strategy.py        # Wildcard/BB/TC/FH optimization
├── utils/
│   ├── config.py               # Strategy configurations
│   └── backtesting.py          # Historical performance testing
└── main.py                     # Entry point
```

## FPL Rules Implemented

### Squad Constraints
- 15-player squad (2 GK, 5 DEF, 5 MID, 3 FWD)
- £100m budget constraint
- Maximum 3 players per team
- Valid formations:
  - 1 GK (always)
  - 3-5 Defenders
  - 2-5 Midfielders
  - 1-3 Forwards

### Transfer Rules
- 1 free transfer per week
- Can bank 1 transfer (max 2)
- -4 points per additional transfer
- Transfer value analysis (worth taking a hit?)

### Chips
- **2 Wildcards** per season (typically GW1-19 and GW20-38)
- **Bench Boost**: All 15 players score points (once)
- **Triple Captain**: Captain scores 3x instead of 2x (once)
- **Free Hit**: Unlimited transfers for 1 week, reverts next week (once)

## Strategy Presets

### Conservative
- 5-gameweek prediction horizon
- Max -4 points on transfers (1 extra transfer)
- Only transfers with clear value
- No differential picks (stick to popular players)
- High chip value thresholds

### Balanced (Default)
- 3-gameweek prediction horizon
- Max -8 points on transfers (2 extra transfers)
- Willing to take calculated hits
- 10% weight on differentials
- Moderate chip thresholds

### Aggressive
- 3-gameweek prediction horizon
- Max -12 points on transfers (3 extra transfers)
- Aggressive transfer strategy
- 25% weight on differentials (low ownership)
- Lower chip thresholds for earlier activation

## Prediction Methodology

### Advanced Forecaster Components

1. **Form Score (35%)**: Exponentially weighted recent games
2. **Points Per Game (20%)**: Season-long average
3. **Fixture Difficulty (25%)**: Opponent strength + position-specific adjustments
4. **Minutes Reliability (10%)**: Consistency of playing time
5. **Consistency (10%)**: Performance variance (penalizes inconsistent players)

### Fixture Analysis
- Difficulty ratings (1-5 scale)
- Home/away splits
- Position-specific:
  - Defenders benefit from weak opposition attacks
  - Forwards benefit from weak opposition defenses
  - Midfielders weighted toward attacking fixtures

## Backtesting

Test your strategies on historical data:

```python
from src.utils.backtesting import Backtester

backtester = Backtester()
result = backtester.run_backtest(
    start_gameweek=1,
    end_gameweek=38,
    initial_squad=my_squad,
    prediction_function=my_predictor
)

backtester.print_backtest_summary(result)
```

## Development Roadmap

- [x] Phase 1: FPL API client and data models
- [x] Phase 2: Basic prediction engine
- [x] Phase 3: Squad optimizer with constraints
- [x] Phase 4: Advanced prediction with historical data
- [x] Phase 5: Transfer planning and multi-week optimization
- [x] Phase 6: Chip strategy optimization
- [x] Phase 7: Backtesting framework
- [ ] Phase 8: Machine learning predictions (xG, xA integration)
- [ ] Phase 9: Live team tracking and weekly automation
- [ ] Phase 10: Web interface / API
- [ ] Phase 11: Monte Carlo simulations for risk analysis

## API Rate Limiting

The FPL API has no official rate limits but be respectful:
- Bootstrap-static data is cached for 5 minutes
- Player details are cached during session
- Consider running optimizer once per day

## Contributing

Contributions welcome! Areas for improvement:
- Machine learning models for predictions
- Expected goals (xG) and expected assists (xA) integration
- Better fixture difficulty calculations
- Historical data storage and analysis
- Web interface

## Disclaimer

This tool is for educational purposes. FPL success depends on many factors including luck, injuries, and real-world football. Use predictions as guidance, not guarantees.

## License

MIT
