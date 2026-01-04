# FPL Optimizer

A Fantasy Premier League squad optimizer that maximizes expected points while respecting all FPL constraints.

## Features

- **FPL API Integration**: Fetch live player data, fixtures, and team information
- **Point Prediction**: Forecast player points based on form and fixture difficulty
- **Squad Optimization**: Linear programming-based optimizer respecting all FPL rules
- **Transfer Planning**: Optimize weekly transfers and chip usage

## Installation

```bash
pip install -r requirements.txt
```

## Quick Start

```bash
python -m src.main
```

## Project Structure

```
src/
├── data/           # FPL API client and data models
├── prediction/     # Player point forecasting
├── optimization/   # Squad and transfer optimization
└── utils/          # Configuration and helpers
```

## FPL Rules Implemented

- 15-player squad (2 GK, 5 DEF, 5 MID, 3 FWD)
- £100m budget constraint
- Maximum 3 players per team
- Valid formations (GK: 1, DEF: 3-5, MID: 2-5, FWD: 1-3)
- 1 free transfer per week (-4 points for additional transfers)

## Development Phases

- [x] Phase 1: FPL API client and data models
- [x] Phase 2: Basic prediction engine
- [x] Phase 3: Squad optimizer with constraints
- [ ] Phase 4: Transfer planning and multi-week optimization
- [ ] Phase 5: Chip strategy (Wildcard, Bench Boost, Triple Captain, Free Hit)

## License

MIT
