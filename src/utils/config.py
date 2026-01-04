"""
Configuration settings for the FPL optimizer.
"""
from dataclasses import dataclass
from typing import Optional


@dataclass
class OptimizerConfig:
    """Configuration for optimizer behavior."""

    # Prediction settings
    prediction_horizon: int = 3  # Gameweeks to predict ahead
    use_advanced_predictions: bool = True  # Use advanced forecaster vs simple
    form_weight: float = 0.35
    fixture_weight: float = 0.25

    # Transfer settings
    max_transfer_cost: int = 8  # Max points to spend on transfers (-4 per transfer)
    transfer_planning_horizon: int = 5  # Gameweeks to plan transfers
    conservative_transfers: bool = True  # Only transfer if clear value

    # Squad optimization
    budget: float = 100.0
    prioritize_starters: bool = True  # Focus on strong starting XI vs bench
    min_squad_value: float = 98.0  # Keep some value in squad for flexibility

    # Chip strategy
    plan_chips: bool = True
    chip_planning_horizon: int = 10  # Gameweeks to look ahead for chip timing
    wildcard_threshold: float = 30.0  # Min value to activate wildcard
    bench_boost_threshold: float = 15.0  # Min bench points to use BB
    triple_captain_threshold: float = 20.0  # Min value for TC
    free_hit_threshold: float = 25.0  # Min value for FH

    # Risk settings
    risk_tolerance: str = 'balanced'  # 'conservative', 'balanced', 'aggressive'
    differential_weight: float = 0.1  # Weight for differential picks (low ownership)

    # Output settings
    verbose: bool = True
    show_detailed_predictions: bool = False


@dataclass
class UserTeamConfig:
    """User's current team configuration."""

    team_id: Optional[int] = None
    current_squad: Optional[list] = None  # List of player IDs
    free_transfers: int = 1
    bank: float = 0.0
    chips_available: list = None  # ['wildcard', 'bboost', '3xc', 'freehit']

    def __post_init__(self):
        if self.chips_available is None:
            self.chips_available = ['wildcard1', 'wildcard2', 'bboost', '3xc', 'freehit']


# Preset configurations
CONSERVATIVE_CONFIG = OptimizerConfig(
    prediction_horizon=5,
    use_advanced_predictions=True,
    max_transfer_cost=4,
    conservative_transfers=True,
    risk_tolerance='conservative',
    differential_weight=0.0,
)

BALANCED_CONFIG = OptimizerConfig(
    prediction_horizon=3,
    use_advanced_predictions=True,
    max_transfer_cost=8,
    conservative_transfers=False,
    risk_tolerance='balanced',
    differential_weight=0.1,
)

AGGRESSIVE_CONFIG = OptimizerConfig(
    prediction_horizon=3,
    use_advanced_predictions=True,
    max_transfer_cost=12,
    conservative_transfers=False,
    risk_tolerance='aggressive',
    differential_weight=0.25,
    wildcard_threshold=20.0,
)


def get_config(preset: str = 'balanced') -> OptimizerConfig:
    """
    Get optimizer configuration.

    Args:
        preset: 'conservative', 'balanced', or 'aggressive'

    Returns:
        OptimizerConfig
    """
    configs = {
        'conservative': CONSERVATIVE_CONFIG,
        'balanced': BALANCED_CONFIG,
        'aggressive': AGGRESSIVE_CONFIG,
    }

    return configs.get(preset.lower(), BALANCED_CONFIG)
