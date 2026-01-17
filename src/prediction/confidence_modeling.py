"""
Prediction confidence and uncertainty modeling.

This module implements Bayesian prediction with confidence intervals,
allowing the optimizer to make risk-aware decisions and properly model
uncertainty that increases with time horizon.
"""
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass
import math
from ..data.models import Player, GameweekData


@dataclass
class PredictionDistribution:
    """
    Represents a prediction as a probability distribution.

    Attributes:
        mean: Expected value (point estimate)
        std_dev: Standard deviation (uncertainty)
        percentile_10: 10th percentile (pessimistic)
        percentile_50: 50th percentile (median, ~= mean)
        percentile_90: 90th percentile (optimistic)
        confidence: Confidence score (0-1, higher = more certain)
    """
    mean: float
    std_dev: float
    percentile_10: float
    percentile_50: float
    percentile_90: float
    confidence: float

    def get_risk_adjusted_value(self, risk_tolerance: str = 'balanced') -> float:
        """
        Get risk-adjusted expected value based on risk tolerance.

        Args:
            risk_tolerance: 'conservative', 'balanced', or 'aggressive'

        Returns:
            Risk-adjusted expected points
        """
        if risk_tolerance == 'conservative':
            # Penalize uncertainty (protect rank)
            return self.mean - 0.5 * self.std_dev
        elif risk_tolerance == 'aggressive':
            # Reward upside potential (climb ranks)
            return self.mean + 0.3 * self.std_dev
        else:  # balanced
            return self.mean


class ConfidenceModeler:
    """
    Models prediction confidence and uncertainty.

    Uncertainty sources:
    1. Time horizon - predictions further out are less certain
    2. Player form variance - inconsistent players harder to predict
    3. Injury/rotation risk - unpredictable selection
    4. Fixture volatility - unpredictable outcomes
    """

    # Base uncertainty per gameweek ahead (increases with distance)
    BASE_UNCERTAINTY_PER_GW = 0.8  # Points std dev per GW ahead

    # Uncertainty growth rate (exponential)
    UNCERTAINTY_GROWTH_RATE = 1.15  # 15% increase per GW

    # Position-specific base uncertainty
    POSITION_BASE_UNCERTAINTY = {
        'GK': 0.5,   # Most consistent (2-6 points usual range)
        'DEF': 0.8,  # Moderate (clean sheets binary)
        'MID': 1.2,  # Higher variance
        'FWD': 1.5,  # Highest variance (goals binary)
    }

    # Minutes uncertainty (higher for rotation risks)
    MINUTES_UNCERTAINTY_FACTOR = 0.15  # 15% uncertainty if rotation risk

    def __init__(self, gameweek_data: GameweekData):
        self.data = gameweek_data

    def calculate_form_variance(self, player: Player, history: Optional[Dict] = None) -> float:
        """
        Calculate player's form variance (consistency measure).

        Args:
            player: Player object
            history: Optional player history dict

        Returns:
            Form variance (higher = more inconsistent)
        """
        if not history or 'history' not in history:
            # Fallback: estimate from season data
            # Assume coefficient of variation ~0.5 for typical player
            return player.points_per_game * 0.5

        recent_games = history['history'][-8:]  # Last 8 games
        if len(recent_games) < 3:
            return player.points_per_game * 0.5

        points = [game['total_points'] for game in recent_games]

        # Calculate standard deviation
        mean_points = sum(points) / len(points)
        variance = sum((p - mean_points) ** 2 for p in points) / len(points)
        std_dev = math.sqrt(variance)

        return std_dev

    def calculate_minutes_uncertainty(
        self,
        player: Player,
        rotation_risk: float = 0.0
    ) -> float:
        """
        Calculate uncertainty from rotation/injury risk.

        Args:
            player: Player object
            rotation_risk: Rotation risk score (0-1)

        Returns:
            Minutes uncertainty contribution
        """
        # Base uncertainty from historical minutes variance
        # Players who don't play 90 consistently have higher uncertainty
        base_uncertainty = 0.5  # Baseline

        # Add rotation risk uncertainty
        rotation_uncertainty = rotation_risk * player.points_per_game * self.MINUTES_UNCERTAINTY_FACTOR

        return base_uncertainty + rotation_uncertainty

    def calculate_fixture_uncertainty(
        self,
        fixture_difficulty: float,
        gameweeks_ahead: int
    ) -> float:
        """
        Calculate uncertainty from fixture difficulty and time horizon.

        Args:
            fixture_difficulty: Fixture difficulty multiplier (0.65 - 1.35)
            gameweeks_ahead: How many GWs in the future

        Returns:
            Fixture uncertainty contribution
        """
        # Hard fixtures have more variance (0-2 pts swings)
        # Easy fixtures still have variance but lower ceiling

        if fixture_difficulty < 0.9:  # Hard fixture
            base_variance = 1.8
        elif fixture_difficulty > 1.15:  # Easy fixture
            base_variance = 1.2
        else:  # Medium fixture
            base_variance = 1.0

        # Increase uncertainty with time horizon (exponential)
        time_factor = self.UNCERTAINTY_GROWTH_RATE ** gameweeks_ahead

        return base_variance * time_factor * 0.3  # Scale down

    def predict_with_confidence(
        self,
        player: Player,
        mean_prediction: float,
        gameweeks_ahead: int = 1,
        form_variance: Optional[float] = None,
        rotation_risk: float = 0.0,
        fixture_difficulty: float = 1.0,
        history: Optional[Dict] = None
    ) -> PredictionDistribution:
        """
        Generate prediction distribution with confidence intervals.

        Args:
            player: Player object
            mean_prediction: Mean expected points (from AdvancedForecaster)
            gameweeks_ahead: Number of gameweeks in future (1 = next GW)
            form_variance: Optional pre-calculated form variance
            rotation_risk: Rotation risk score (0-1)
            fixture_difficulty: Fixture difficulty multiplier
            history: Optional player history for variance calculation

        Returns:
            PredictionDistribution with mean, std_dev, percentiles
        """
        # Calculate form variance if not provided
        if form_variance is None:
            form_variance = self.calculate_form_variance(player, history)

        # Calculate uncertainty components

        # 1. Time horizon uncertainty (base)
        time_uncertainty = (
            self.BASE_UNCERTAINTY_PER_GW *
            (self.UNCERTAINTY_GROWTH_RATE ** gameweeks_ahead)
        )

        # 2. Position-specific base uncertainty
        position_uncertainty = self.POSITION_BASE_UNCERTAINTY[player.position]

        # 3. Form variance (player consistency)
        form_uncertainty = form_variance * 0.6  # Scale down for per-GW

        # 4. Minutes/rotation uncertainty
        minutes_uncertainty = self.calculate_minutes_uncertainty(player, rotation_risk)

        # 5. Fixture uncertainty
        fixture_uncertainty = self.calculate_fixture_uncertainty(
            fixture_difficulty,
            gameweeks_ahead
        )

        # Combine uncertainties (variance adds, so std_dev is sqrt of sum of squares)
        total_variance = (
            time_uncertainty ** 2 +
            position_uncertainty ** 2 +
            form_uncertainty ** 2 +
            minutes_uncertainty ** 2 +
            fixture_uncertainty ** 2
        )

        std_dev = math.sqrt(total_variance)

        # Calculate percentiles (assuming normal distribution)
        # 10th percentile: mean - 1.28 * std_dev
        # 50th percentile: mean (median)
        # 90th percentile: mean + 1.28 * std_dev

        percentile_10 = max(0, mean_prediction - 1.28 * std_dev)
        percentile_50 = mean_prediction
        percentile_90 = mean_prediction + 1.28 * std_dev

        # Calculate confidence score (0-1)
        # Lower std_dev relative to mean = higher confidence
        # confidence = 1 / (1 + (std_dev / mean))
        if mean_prediction > 0:
            confidence = 1.0 / (1.0 + (std_dev / mean_prediction))
        else:
            confidence = 0.5  # Neutral confidence for zero predictions

        return PredictionDistribution(
            mean=round(mean_prediction, 2),
            std_dev=round(std_dev, 2),
            percentile_10=round(percentile_10, 2),
            percentile_50=round(percentile_50, 2),
            percentile_90=round(percentile_90, 2),
            confidence=round(confidence, 3)
        )

    def predict_multi_gameweek_distribution(
        self,
        player: Player,
        gameweek_predictions: List[float],
        rotation_risks: List[float],
        fixture_difficulties: List[float],
        history: Optional[Dict] = None
    ) -> PredictionDistribution:
        """
        Generate distribution for cumulative multi-gameweek prediction.

        Args:
            player: Player object
            gameweek_predictions: List of mean predictions per GW
            rotation_risks: List of rotation risks per GW
            fixture_difficulties: List of fixture difficulties per GW
            history: Optional player history

        Returns:
            PredictionDistribution for cumulative points
        """
        if not gameweek_predictions:
            return PredictionDistribution(0, 0, 0, 0, 0, 0)

        # Calculate form variance once
        form_variance = self.calculate_form_variance(player, history)

        # Generate distributions for each GW
        distributions = []
        for i, (pred, rot_risk, fix_diff) in enumerate(
            zip(gameweek_predictions, rotation_risks, fixture_difficulties)
        ):
            dist = self.predict_with_confidence(
                player,
                mean_prediction=pred,
                gameweeks_ahead=i + 1,  # 1-indexed
                form_variance=form_variance,
                rotation_risk=rot_risk,
                fixture_difficulty=fix_diff,
                history=history
            )
            distributions.append(dist)

        # Aggregate distributions
        # Mean: sum of means
        # Variance: sum of variances (independent events)
        # Std dev: sqrt(sum of variances)

        total_mean = sum(d.mean for d in distributions)
        total_variance = sum(d.std_dev ** 2 for d in distributions)
        total_std_dev = math.sqrt(total_variance)

        # Calculate aggregate percentiles
        percentile_10 = max(0, total_mean - 1.28 * total_std_dev)
        percentile_50 = total_mean
        percentile_90 = total_mean + 1.28 * total_std_dev

        # Aggregate confidence (average, weighted by prediction magnitude)
        if total_mean > 0:
            weighted_confidence = sum(
                d.confidence * d.mean for d in distributions
            ) / total_mean
        else:
            weighted_confidence = 0.5

        return PredictionDistribution(
            mean=round(total_mean, 2),
            std_dev=round(total_std_dev, 2),
            percentile_10=round(percentile_10, 2),
            percentile_50=round(percentile_50, 2),
            percentile_90=round(percentile_90, 2),
            confidence=round(weighted_confidence, 3)
        )

    def compare_players_with_risk(
        self,
        player_a: Tuple[Player, PredictionDistribution],
        player_b: Tuple[Player, PredictionDistribution],
        risk_tolerance: str = 'balanced'
    ) -> str:
        """
        Compare two players considering risk tolerance.

        Args:
            player_a: (Player, PredictionDistribution)
            player_b: (Player, PredictionDistribution)
            risk_tolerance: 'conservative', 'balanced', or 'aggressive'

        Returns:
            'A' if player A is better, 'B' if player B is better
        """
        _, dist_a = player_a
        _, dist_b = player_b

        value_a = dist_a.get_risk_adjusted_value(risk_tolerance)
        value_b = dist_b.get_risk_adjusted_value(risk_tolerance)

        return 'A' if value_a > value_b else 'B'

    def calculate_transfer_value_with_uncertainty(
        self,
        player_in_dist: PredictionDistribution,
        player_out_dist: PredictionDistribution,
        transfer_cost: int,
        risk_tolerance: str = 'balanced'
    ) -> Tuple[float, float]:
        """
        Calculate transfer value considering uncertainty.

        Args:
            player_in_dist: Distribution for incoming player
            player_out_dist: Distribution for outgoing player
            transfer_cost: Points cost (-4 per hit)
            risk_tolerance: Risk tolerance setting

        Returns:
            (expected_value, confidence) tuple
        """
        # Get risk-adjusted values
        value_in = player_in_dist.get_risk_adjusted_value(risk_tolerance)
        value_out = player_out_dist.get_risk_adjusted_value(risk_tolerance)

        # Calculate net value
        net_value = value_in - value_out - abs(transfer_cost)

        # Calculate confidence in transfer decision
        # Higher confidence if:
        # 1. Both players have high individual confidence
        # 2. Value gap is large relative to uncertainty

        avg_confidence = (player_in_dist.confidence + player_out_dist.confidence) / 2

        # Value gap relative to combined uncertainty
        combined_std = math.sqrt(
            player_in_dist.std_dev ** 2 + player_out_dist.std_dev ** 2
        )

        if combined_std > 0:
            # How many std devs is the value gap?
            # If gap is 10 pts and combined std is 2 pts, that's 5 std devs (very confident)
            std_devs_gap = abs(value_in - value_out) / combined_std
            confidence_boost = min(std_devs_gap / 3.0, 1.0)  # Cap at 1.0
        else:
            confidence_boost = 0.5

        # Combine confidence measures
        transfer_confidence = (avg_confidence + confidence_boost) / 2

        return round(net_value, 2), round(transfer_confidence, 3)


def get_risk_tolerance_description(risk_tolerance: str) -> str:
    """Get human-readable description of risk tolerance."""
    descriptions = {
        'conservative': (
            "Conservative: Minimize downside risk, protect rank. "
            "Prefers consistent, low-variance players."
        ),
        'balanced': (
            "Balanced: Expected value optimization. "
            "Standard risk/reward tradeoff."
        ),
        'aggressive': (
            "Aggressive: Maximize upside potential, climb ranks. "
            "Takes calculated risks for high-reward outcomes."
        )
    }
    return descriptions.get(risk_tolerance, descriptions['balanced'])
