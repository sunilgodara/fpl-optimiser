"""
Rank projection and risk modeling for FPL optimization.

This module enables rank-aware optimization:
- Defending top ranks: Low variance, template squad
- Climbing ranks: Differentials + calculated risks
- Monte Carlo rank simulation
"""
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass
import math
import random
from ..data.models import Player, GameweekData


@dataclass
class RankProjection:
    """
    Rank projection with confidence intervals.

    Attributes:
        current_rank: Current overall rank
        projected_rank: Expected rank after strategy
        best_case_rank: 90th percentile (optimistic)
        worst_case_rank: 10th percentile (pessimistic)
        expected_points: Expected total points
        differential_score: How different from template (0-1)
        risk_level: Risk assessment (low/medium/high)
    """
    current_rank: int
    projected_rank: int
    best_case_rank: int
    worst_case_rank: int
    expected_points: float
    differential_score: float
    risk_level: str

    def rank_change(self) -> int:
        """Calculate expected rank change (negative = improvement)."""
        return self.projected_rank - self.current_rank

    def best_case_change(self) -> int:
        """Best case rank change."""
        return self.best_case_rank - self.current_rank

    def worst_case_change(self) -> int:
        """Worst case rank change."""
        return self.worst_case_rank - self.current_rank


class RankProjector:
    """
    Projects future rank based on squad decisions and risk tolerance.

    Uses Monte Carlo simulation to model rank distribution.
    """

    # Average points by rank bracket (approximate)
    RANK_BRACKETS = {
        'top_1k': 2400,      # Elite
        'top_10k': 2300,     # Excellent
        'top_100k': 2150,    # Very good
        'top_500k': 2000,    # Good
        'top_1m': 1900,      # Average
        'below_1m': 1800,    # Below average
    }

    # Points variance by rank bracket (std dev)
    RANK_VARIANCE = {
        'top_1k': 50,        # Very consistent
        'top_10k': 80,       # Consistent
        'top_100k': 120,     # Moderate variance
        'top_500k': 150,     # Higher variance
        'top_1m': 180,       # High variance
        'below_1m': 200,     # Very high variance
    }

    def __init__(self, gameweek_data: GameweekData):
        self.data = gameweek_data
        self.total_players = 10_000_000  # Approximate FPL player count

    def _get_rank_bracket(self, rank: int) -> str:
        """
        Get rank bracket for a given rank.

        Args:
            rank: Overall rank

        Returns:
            Bracket name
        """
        if rank <= 1_000:
            return 'top_1k'
        elif rank <= 10_000:
            return 'top_10k'
        elif rank <= 100_000:
            return 'top_100k'
        elif rank <= 500_000:
            return 'top_500k'
        elif rank <= 1_000_000:
            return 'top_1m'
        else:
            return 'below_1m'

    def _estimate_points_from_rank(self, rank: int, gws_played: int = 20) -> float:
        """
        Estimate total points from rank and gameweeks played.

        Args:
            rank: Overall rank
            gws_played: Gameweeks played so far

        Returns:
            Estimated total points
        """
        bracket = self._get_rank_bracket(rank)
        season_pts = self.RANK_BRACKETS[bracket]

        # Scale to GWs played
        estimated_pts = (season_pts / 38) * gws_played

        return estimated_pts

    def _simulate_rank_distribution(
        self,
        current_rank: int,
        points_delta: float,
        variance: float,
        num_simulations: int = 10000
    ) -> List[int]:
        """
        Monte Carlo simulation of rank distribution.

        Args:
            current_rank: Current overall rank
            points_delta: Expected points gain
            variance: Uncertainty in points (std dev)
            num_simulations: Number of simulations

        Returns:
            List of simulated final ranks
        """
        current_bracket = self._get_rank_bracket(current_rank)
        bracket_variance = self.RANK_VARIANCE[current_bracket]

        simulated_ranks = []

        for _ in range(num_simulations):
            # Simulate points gain (normal distribution)
            actual_delta = random.gauss(points_delta, variance)

            # Simulate opponent points (also variable)
            opponent_variance = bracket_variance
            opponent_delta = random.gauss(0, opponent_variance)

            # Net relative gain
            relative_gain = actual_delta - opponent_delta

            # Convert points gain to rank change
            # Rough heuristic: 1 point = ~10,000 ranks in mid-table
            # Scales with rank bracket
            if current_rank <= 10_000:
                pts_per_rank = 0.01  # Very tight
            elif current_rank <= 100_000:
                pts_per_rank = 0.05  # Tight
            elif current_rank <= 500_000:
                pts_per_rank = 0.1   # Moderate
            else:
                pts_per_rank = 0.2   # Looser

            rank_change = int(-relative_gain / pts_per_rank)

            # Calculate new rank
            new_rank = max(1, min(self.total_players, current_rank + rank_change))
            simulated_ranks.append(new_rank)

        return simulated_ranks

    def project_rank(
        self,
        current_rank: int,
        squad_expected_points: float,
        template_expected_points: float,
        differential_score: float,
        gws_remaining: int = 18,
        risk_tolerance: str = 'balanced'
    ) -> RankProjection:
        """
        Project rank based on squad decisions.

        Args:
            current_rank: Current overall rank
            squad_expected_points: Expected points from your squad
            template_expected_points: Expected points from template squad
            differential_score: How different from template (0-1, higher = more different)
            gws_remaining: Gameweeks remaining in season
            risk_tolerance: Risk tolerance ('conservative', 'balanced', 'aggressive')

        Returns:
            RankProjection with confidence intervals
        """
        # Calculate points delta vs template
        points_delta = squad_expected_points - template_expected_points

        # Variance increases with differentials
        # Template squad = low variance (std dev ~15% of delta)
        # High differentials = high variance (std dev ~40% of delta)
        base_variance = abs(points_delta) * 0.15
        differential_variance = abs(points_delta) * differential_score * 0.25
        total_variance = base_variance + differential_variance

        # Run Monte Carlo simulation
        simulated_ranks = self._simulate_rank_distribution(
            current_rank,
            points_delta * gws_remaining,  # Scale to season
            total_variance * math.sqrt(gws_remaining),  # Variance grows with time
            num_simulations=10000
        )

        # Calculate percentiles
        simulated_ranks.sort()
        projected_rank = simulated_ranks[5000]  # Median (50th percentile)
        best_case_rank = simulated_ranks[1000]  # 10th percentile (optimistic)
        worst_case_rank = simulated_ranks[9000]  # 90th percentile (pessimistic)

        # Assess risk level
        rank_spread = worst_case_rank - best_case_rank
        if rank_spread < 50_000:
            risk_level = 'low'
        elif rank_spread < 150_000:
            risk_level = 'medium'
        else:
            risk_level = 'high'

        return RankProjection(
            current_rank=current_rank,
            projected_rank=projected_rank,
            best_case_rank=best_case_rank,
            worst_case_rank=worst_case_rank,
            expected_points=squad_expected_points * gws_remaining,
            differential_score=round(differential_score, 2),
            risk_level=risk_level
        )

    def recommend_strategy(
        self,
        current_rank: int,
        target_rank: Optional[int] = None
    ) -> Dict[str, any]:
        """
        Recommend strategy based on current rank and goals.

        Args:
            current_rank: Current overall rank
            target_rank: Target rank (if None, auto-detect)

        Returns:
            Strategy recommendation dict
        """
        bracket = self._get_rank_bracket(current_rank)

        # Auto-detect target if not specified
        if target_rank is None:
            if bracket == 'below_1m':
                target_rank = 500_000  # Target: Top 500k
            elif bracket == 'top_1m':
                target_rank = 100_000  # Target: Top 100k
            elif bracket == 'top_500k':
                target_rank = 50_000   # Target: Top 50k
            elif bracket == 'top_100k':
                target_rank = 10_000   # Target: Top 10k
            else:
                target_rank = max(1_000, current_rank // 2)  # Aim to halve rank

        rank_gap = current_rank - target_rank

        # Determine required strategy
        if rank_gap < 0:
            # Already at or above target - DEFEND
            strategy = {
                'mode': 'defensive',
                'risk_tolerance': 'conservative',
                'differential_target': 0.1,  # 10% differentials
                'template_match_target': 0.9,  # 90% template
                'description': 'Defend your rank',
                'recommendations': [
                    'Stick closely to template players',
                    'Minimize variance and downside risk',
                    'Focus on consistent performers',
                    'Avoid risky differentials',
                    'Use chips strategically on template timing'
                ]
            }
        elif rank_gap < 50_000:
            # Small climb - STEADY IMPROVEMENT
            strategy = {
                'mode': 'steady',
                'risk_tolerance': 'balanced',
                'differential_target': 0.25,  # 25% differentials
                'template_match_target': 0.75,  # 75% template
                'description': 'Steady improvement with calculated risks',
                'recommendations': [
                    'Mix template players with value differentials',
                    'Target undervalued players in good form',
                    'Balance risk and consistency',
                    'Look for fixture swing opportunities',
                    'Time chips for maximum differential gain'
                ]
            }
        elif rank_gap < 200_000:
            # Moderate climb - AGGRESSIVE BUT SMART
            strategy = {
                'mode': 'aggressive',
                'risk_tolerance': 'aggressive',
                'differential_target': 0.4,  # 40% differentials
                'template_match_target': 0.6,  # 60% template
                'description': 'Aggressive strategy with smart differentials',
                'recommendations': [
                    'Take calculated risks on differentials',
                    'Target fixture swings ahead of template',
                    'Consider contrarian captaincy choices',
                    'Use chips to maximize differential advantage',
                    'Prioritize upside potential over consistency'
                ]
            }
        else:
            # Large climb - HIGH RISK/HIGH REWARD
            strategy = {
                'mode': 'high_risk',
                'risk_tolerance': 'aggressive',
                'differential_target': 0.5,  # 50% differentials
                'template_match_target': 0.5,  # 50% template
                'description': 'High risk/high reward punts needed',
                'recommendations': [
                    'Take significant differential risks',
                    'Identify template players BEFORE they become template',
                    'Aggressive captaincy differentials',
                    'Early chip usage for maximum gain',
                    'Accept high variance for upside potential',
                    'Target form players in explosive teams'
                ]
            }

        strategy['current_rank'] = current_rank
        strategy['target_rank'] = target_rank
        strategy['rank_gap'] = rank_gap

        return strategy

    def compare_squads_by_rank_impact(
        self,
        current_rank: int,
        squad_a: Dict[str, any],
        squad_b: Dict[str, any],
        template_expected_points: float,
        gws_remaining: int = 18
    ) -> Dict[str, any]:
        """
        Compare two squads by their rank impact.

        Args:
            current_rank: Current overall rank
            squad_a: {'expected_points': float, 'differential_score': float, 'name': str}
            squad_b: Similar to squad_a
            template_expected_points: Expected points from template
            gws_remaining: GWs remaining

        Returns:
            Comparison with rank projections
        """
        proj_a = self.project_rank(
            current_rank,
            squad_a['expected_points'],
            template_expected_points,
            squad_a['differential_score'],
            gws_remaining
        )

        proj_b = self.project_rank(
            current_rank,
            squad_b['expected_points'],
            template_expected_points,
            squad_b['differential_score'],
            gws_remaining
        )

        # Determine winner
        if proj_a.projected_rank < proj_b.projected_rank:
            winner = 'A'
            winner_name = squad_a.get('name', 'Squad A')
        else:
            winner = 'B'
            winner_name = squad_b.get('name', 'Squad B')

        return {
            'squad_a': {
                'name': squad_a.get('name', 'Squad A'),
                'projection': proj_a,
                'points': squad_a['expected_points'],
                'differential_score': squad_a['differential_score']
            },
            'squad_b': {
                'name': squad_b.get('name', 'Squad B'),
                'projection': proj_b,
                'points': squad_b['expected_points'],
                'differential_score': squad_b['differential_score']
            },
            'winner': winner,
            'winner_name': winner_name,
            'rank_difference': abs(proj_a.projected_rank - proj_b.projected_rank)
        }


def format_rank(rank: int) -> str:
    """Format rank with commas for readability."""
    return f"{rank:,}"


def print_rank_projection(projection: RankProjection):
    """Print formatted rank projection."""
    print(f"\nRANK PROJECTION")
    print("=" * 60)
    print(f"Current Rank: {format_rank(projection.current_rank)}")
    print(f"Projected Rank: {format_rank(projection.projected_rank)} ({projection.rank_change():+,} change)")
    print(f"\nConfidence Interval:")
    print(f"  Best Case (10th %ile): {format_rank(projection.best_case_rank)} ({projection.best_case_change():+,})")
    print(f"  Expected (50th %ile): {format_rank(projection.projected_rank)} ({projection.rank_change():+,})")
    print(f"  Worst Case (90th %ile): {format_rank(projection.worst_case_rank)} ({projection.worst_case_change():+,})")
    print(f"\nExpected Points: {projection.expected_points:.1f}")
    print(f"Differential Score: {projection.differential_score:.1%}")
    print(f"Risk Level: {projection.risk_level.upper()}")
    print("=" * 60)
