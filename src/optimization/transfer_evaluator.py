"""
Enhanced transfer valuation with comprehensive value modeling.

This module implements sophisticated transfer value calculations that consider:
- Expected points gain over multiple gameweeks
- Price change value
- Squad flexibility
- Chip synergy
- Fixture swing duration
"""
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass
import math
from ..data.models import Player, GameweekData, Fixture


@dataclass
class TransferValue:
    """
    Comprehensive transfer value breakdown.

    Attributes:
        points_gain: Expected points gain over horizon
        fixture_swing_duration: How many GWs does fixture advantage last
        price_change_value: Expected value from price changes
        flexibility_value: Squad flexibility improvement
        chip_synergy_value: Value if transfer synergizes with chip plan
        transfer_cost: Cost in points (-4 per hit)
        total_value: Net total value
        confidence: Confidence in valuation (0-1)
    """
    points_gain: float
    fixture_swing_duration: int
    price_change_value: float
    flexibility_value: float
    chip_synergy_value: float
    transfer_cost: int
    total_value: float
    confidence: float

    def is_worth_hit(self) -> bool:
        """Check if transfer is worth a -4 hit."""
        return self.total_value > 0

    def payback_gameweeks(self) -> Optional[int]:
        """
        Calculate how many GWs to recover transfer cost.

        Returns:
            Number of GWs to break even, or None if never breaks even
        """
        if self.points_gain <= 0:
            return None

        avg_gain_per_gw = self.points_gain / max(self.fixture_swing_duration, 1)
        if avg_gain_per_gw <= 0:
            return None

        hit_cost = abs(self.transfer_cost)
        payback_gws = math.ceil(hit_cost / avg_gain_per_gw)

        return payback_gws


class TransferEvaluator:
    """
    Evaluates transfer value with comprehensive modeling.

    Key features:
    1. Multi-gameweek expected points gain
    2. Fixture swing duration analysis
    3. Price change probability and value
    4. Squad flexibility scoring
    5. Chip synergy detection
    """

    # Price change thresholds (simplified model)
    PRICE_RISE_PROBABILITY = {
        'high_ownership_gain': 0.7,   # 70% chance if ownership rising fast
        'medium_ownership_gain': 0.3, # 30% chance if moderate rise
        'low_ownership_gain': 0.1,    # 10% chance if slight rise
    }

    PRICE_DROP_PROBABILITY = {
        'high_ownership_loss': 0.6,   # 60% chance if ownership dropping fast
        'medium_ownership_loss': 0.25, # 25% chance if moderate drop
        'low_ownership_loss': 0.05,    # 5% chance if slight drop
    }

    # Flexibility value parameters
    FLEXIBILITY_BASE_VALUE = 2.0  # Base value for flexible squad structure
    FLEXIBILITY_PREMIUM_POSITIONS = ['MID', 'FWD']  # Positions that offer more flexibility

    def __init__(self, gameweek_data: GameweekData):
        self.data = gameweek_data

    def calculate_fixture_swing_duration(
        self,
        player: Player,
        fixtures: List[Fixture],
        difficulty_threshold: float = 1.15
    ) -> int:
        """
        Calculate how many consecutive GWs the player has favorable fixtures.

        Args:
            player: Player to analyze
            fixtures: List of upcoming fixtures for player's team
            difficulty_threshold: Threshold for "favorable" (multiplier > threshold)

        Returns:
            Number of consecutive favorable GWs
        """
        duration = 0

        for fixture in fixtures:
            # Calculate fixture difficulty
            is_home = fixture.team_h == player.team_id
            difficulty = fixture.team_h_difficulty if is_home else fixture.team_a_difficulty

            # Simplified difficulty to multiplier mapping
            if difficulty <= 2:
                fixture_mult = 1.25  # Easy
            elif difficulty == 3:
                fixture_mult = 1.0   # Medium
            else:
                fixture_mult = 0.75  # Hard

            if fixture_mult >= difficulty_threshold:
                duration += 1
            else:
                # Swing ends at first non-favorable fixture
                break

        return max(duration, 1)  # At least 1 GW

    def estimate_price_change_value(
        self,
        player_in: Player,
        player_out: Player,
        horizon_gws: int = 5
    ) -> Tuple[float, float]:
        """
        Estimate value from price changes.

        Args:
            player_in: Incoming player
            player_out: Outgoing player
            horizon_gws: Gameweeks to look ahead

        Returns:
            (price_change_value, confidence) tuple
        """
        # Incoming player price change value
        in_rise_prob = self._estimate_rise_probability(player_in)
        in_expected_rises = in_rise_prob * horizon_gws * 0.3  # Avg 0.3 rises in horizon
        in_value = in_expected_rises * 0.1  # Each rise = +£0.1m locked value

        # Outgoing player price drop avoidance
        out_drop_prob = self._estimate_drop_probability(player_out)
        out_expected_drops = out_drop_prob * horizon_gws * 0.2  # Avg 0.2 drops avoided
        out_value = out_expected_drops * 0.1  # Each drop avoided = +£0.1m saved

        total_value = (in_value + out_value) * 5  # Convert £0.1m to ~5 points value

        # Confidence based on ownership trends
        confidence = (in_rise_prob + (1 - out_drop_prob)) / 2

        return round(total_value, 2), round(confidence, 2)

    def _estimate_rise_probability(self, player: Player) -> float:
        """
        Estimate probability of price rise based on ownership and form.

        Simple heuristic:
        - High ownership change + good form = likely rise
        - Low ownership or poor form = unlikely rise
        """
        # Check if player is in form (PPG > 5.0 and form > 5.0)
        if player.points_per_game > 5.0 and player.form > 5.0:
            # High performers likely to rise
            if player.selected_by > 15.0:  # High ownership
                return 0.5  # Medium-high probability
            else:
                return 0.3  # Medium probability (template player)
        elif player.points_per_game > 4.0:
            return 0.2  # Low probability
        else:
            return 0.05  # Very low probability

    def _estimate_drop_probability(self, player: Player) -> float:
        """
        Estimate probability of price drop based on ownership and form.

        Simple heuristic:
        - Poor form + high ownership = likely drop
        - Good form or low ownership = unlikely drop
        """
        # Check if player is out of form (PPG < 3.0 or form < 2.0)
        if player.points_per_game < 3.0 or player.form < 2.0:
            # Poor performers likely to drop
            if player.selected_by > 10.0:  # Significant ownership
                return 0.4  # Medium-high probability
            else:
                return 0.2  # Low-medium probability
        else:
            return 0.05  # Very low probability

    def calculate_squad_flexibility_value(
        self,
        player_in: Player,
        current_squad: List[Player],
        target_formation: str = '3-4-3'
    ) -> float:
        """
        Calculate squad flexibility improvement from transfer.

        Args:
            player_in: Incoming player
            current_squad: Current 15-player squad
            target_formation: Target formation (e.g., '3-4-3')

        Returns:
            Flexibility value (0-5 points)
        """
        flexibility_value = 0.0

        # Count positions in current squad
        position_counts = {
            'GK': sum(1 for p in current_squad if p.position == 'GK'),
            'DEF': sum(1 for p in current_squad if p.position == 'DEF'),
            'MID': sum(1 for p in current_squad if p.position == 'MID'),
            'FWD': sum(1 for p in current_squad if p.position == 'FWD'),
        }

        # Ideal counts: 2 GK, 5 DEF, 5 MID, 3 FWD
        ideal_counts = {'GK': 2, 'DEF': 5, 'MID': 5, 'FWD': 3}

        # Check if new player improves positional balance
        current_balance_error = sum(
            abs(position_counts.get(pos, 0) - ideal_counts[pos])
            for pos in ideal_counts
        )

        # Simulate adding new player
        new_counts = position_counts.copy()
        new_counts[player_in.position] = new_counts.get(player_in.position, 0) + 1

        new_balance_error = sum(
            abs(new_counts.get(pos, 0) - ideal_counts[pos])
            for pos in ideal_counts
        )

        # Reward if balance improves
        if new_balance_error < current_balance_error:
            flexibility_value += self.FLEXIBILITY_BASE_VALUE

        # Bonus for premium flexible positions
        if player_in.position in self.FLEXIBILITY_PREMIUM_POSITIONS:
            flexibility_value += 0.5

        # Bonus for mid-priced players (enable better squad building)
        if 5.0 <= player_in.price <= 7.5:
            flexibility_value += 0.5

        return round(flexibility_value, 2)

    def calculate_chip_synergy_value(
        self,
        player_in: Player,
        chip_plan: Optional[Dict[int, str]],
        current_gw: int,
        player_in_predictions: Dict[int, float]
    ) -> float:
        """
        Calculate value if transfer synergizes with upcoming chip usage.

        Args:
            player_in: Incoming player
            chip_plan: Dict mapping GW to chip name (e.g., {25: 'bboost'})
            current_gw: Current gameweek
            player_in_predictions: Predictions for incoming player by GW

        Returns:
            Chip synergy value
        """
        if not chip_plan:
            return 0.0

        synergy_value = 0.0

        # Check if any chips planned in next 5 GWs
        upcoming_chips = {
            gw: chip for gw, chip in chip_plan.items()
            if current_gw <= gw <= current_gw + 5
        }

        for chip_gw, chip_name in upcoming_chips.items():
            if chip_name == 'wildcard':
                # Don't value transfers before wildcard (WC rebuilds anyway)
                synergy_value -= 2.0
            elif chip_name == 'bboost':
                # Value bench-quality players more before Bench Boost
                if player_in.price < 6.0:  # Bench player
                    predicted_pts = player_in_predictions.get(chip_gw, 0)
                    if predicted_pts > 4.0:  # Good bench boost option
                        synergy_value += 3.0
            elif chip_name == '3xc':
                # Value premium captaincy options more before Triple Captain
                if player_in.price >= 11.0:  # Premium player
                    predicted_pts = player_in_predictions.get(chip_gw, 0)
                    if predicted_pts > 15.0:  # TC worthy
                        synergy_value += 2.0
            elif chip_name == 'freehit':
                # Free hit means we get this player back, so no long-term value
                synergy_value -= 1.0

        return round(synergy_value, 2)

    def evaluate_transfer(
        self,
        player_in: Player,
        player_out: Player,
        player_in_predictions: Dict[int, float],
        player_out_predictions: Dict[int, float],
        current_squad: List[Player],
        fixtures_in: List[Fixture],
        fixtures_out: List[Fixture],
        transfer_cost: int = 0,
        chip_plan: Optional[Dict[int, str]] = None,
        horizon_gws: int = 5
    ) -> TransferValue:
        """
        Comprehensive transfer evaluation.

        Args:
            player_in: Incoming player
            player_out: Outgoing player
            player_in_predictions: Predictions by GW for incoming player
            player_out_predictions: Predictions by GW for outgoing player
            current_squad: Current 15-player squad
            fixtures_in: Upcoming fixtures for incoming player's team
            fixtures_out: Upcoming fixtures for outgoing player's team
            transfer_cost: Cost in points (0 for free, -4 for hit)
            chip_plan: Optional chip plan
            horizon_gws: Gameweeks to evaluate over

        Returns:
            TransferValue with comprehensive breakdown
        """
        current_gw = self.data.current_gameweek

        # 1. Calculate expected points gain over horizon
        points_gain = 0.0
        for gw in range(current_gw, current_gw + horizon_gws):
            in_pts = player_in_predictions.get(gw, 0)
            out_pts = player_out_predictions.get(gw, 0)
            points_gain += (in_pts - out_pts)

        # 2. Calculate fixture swing duration
        fixture_swing_in = self.calculate_fixture_swing_duration(
            player_in,
            fixtures_in[:horizon_gws]
        )
        fixture_swing_out = self.calculate_fixture_swing_duration(
            player_out,
            fixtures_out[:horizon_gws]
        )

        # Use incoming player's fixture swing as primary metric
        fixture_swing_duration = fixture_swing_in

        # 3. Calculate price change value
        price_change_value, price_confidence = self.estimate_price_change_value(
            player_in,
            player_out,
            horizon_gws
        )

        # 4. Calculate squad flexibility value
        flexibility_value = self.calculate_squad_flexibility_value(
            player_in,
            current_squad
        )

        # 5. Calculate chip synergy value
        chip_synergy_value = self.calculate_chip_synergy_value(
            player_in,
            chip_plan,
            current_gw,
            player_in_predictions
        )

        # 6. Calculate total value
        total_value = (
            points_gain +
            price_change_value +
            flexibility_value +
            chip_synergy_value +
            transfer_cost  # Already negative if hit
        )

        # 7. Calculate confidence
        # High confidence if:
        # - Large points gain
        # - Long fixture swing
        # - High price change confidence
        base_confidence = 0.5
        if points_gain > 10:
            base_confidence += 0.2
        if fixture_swing_duration >= 3:
            base_confidence += 0.15
        base_confidence += price_confidence * 0.15

        confidence = min(base_confidence, 1.0)

        return TransferValue(
            points_gain=round(points_gain, 2),
            fixture_swing_duration=fixture_swing_duration,
            price_change_value=round(price_change_value, 2),
            flexibility_value=round(flexibility_value, 2),
            chip_synergy_value=round(chip_synergy_value, 2),
            transfer_cost=transfer_cost,
            total_value=round(total_value, 2),
            confidence=round(confidence, 3)
        )

    def rank_transfer_candidates(
        self,
        transfer_evaluations: List[Tuple[Player, Player, TransferValue]],
        min_value: float = 0.0,
        sort_by: str = 'total_value'
    ) -> List[Tuple[Player, Player, TransferValue]]:
        """
        Rank transfer candidates by value.

        Args:
            transfer_evaluations: List of (player_in, player_out, TransferValue)
            min_value: Minimum total value to include
            sort_by: Metric to sort by ('total_value', 'points_gain', 'confidence')

        Returns:
            Sorted list of transfer evaluations
        """
        # Filter by minimum value
        candidates = [
            (pin, pout, val) for pin, pout, val in transfer_evaluations
            if val.total_value >= min_value
        ]

        # Sort by specified metric
        if sort_by == 'total_value':
            candidates.sort(key=lambda x: x[2].total_value, reverse=True)
        elif sort_by == 'points_gain':
            candidates.sort(key=lambda x: x[2].points_gain, reverse=True)
        elif sort_by == 'confidence':
            candidates.sort(
                key=lambda x: (x[2].confidence, x[2].total_value),
                reverse=True
            )

        return candidates

    def find_bridge_players(
        self,
        available_players: List[Player],
        short_term_horizon: int = 3,
        long_term_horizon: int = 8,
        price_range: Tuple[float, float] = (5.0, 8.0)
    ) -> List[Player]:
        """
        Find "bridge players" - good for short-term while building towards long-term template.

        Bridge players are:
        - Mid-priced (affordable, don't lock too much value)
        - Good short-term fixtures (3-5 GWs)
        - Reasonable long-term option or easy to transfer out

        Args:
            available_players: List of available players
            short_term_horizon: GWs for short-term analysis
            long_term_horizon: GWs for long-term analysis
            price_range: (min_price, max_price) for bridge players

        Returns:
            List of bridge player candidates
        """
        bridge_candidates = []

        for player in available_players:
            # Must be in price range
            if not (price_range[0] <= player.price <= price_range[1]):
                continue

            # Must have decent PPG
            if player.points_per_game < 4.0:
                continue

            # Check short-term fixtures (simplified)
            # In real implementation, would use fixture difficulty calculator
            if player.form > 4.0:  # Good recent form
                bridge_candidates.append(player)

        return bridge_candidates
