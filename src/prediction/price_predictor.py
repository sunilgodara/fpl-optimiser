"""
Price change prediction for FPL players.
Helps managers avoid losing team value and capitalize on price rises.
"""
from typing import Dict, List, Tuple, Optional
from ..data.models import Player, GameweekData
from datetime import datetime


class PricePredictor:
    """
    Predicts player price changes based on ownership trends.

    FPL price changes occur daily (~1:30am GMT) based on net transfers:
    - Players with high net transfers IN → price rise
    - Players with high net transfers OUT → price drop

    Key factors:
    - Ownership change rate (% TSB change)
    - Current price tier (cheaper players change faster)
    - Recent form and fixtures (drives transfers)
    - Injury/suspension news
    """

    # Price change thresholds (simplified model)
    # In reality, FPL uses a complex proprietary algorithm
    # These are community-researched approximations

    # Ownership change thresholds for price rise/drop
    RISE_THRESHOLD_HIGH = 100.0    # Very likely to rise (>100 net transfers per 1% owned)
    RISE_THRESHOLD_MEDIUM = 50.0   # Likely to rise
    RISE_THRESHOLD_LOW = 25.0      # Possibly rising

    DROP_THRESHOLD_HIGH = -100.0   # Very likely to drop
    DROP_THRESHOLD_MEDIUM = -50.0  # Likely to drop
    DROP_THRESHOLD_LOW = -25.0     # Possibly dropping

    # Price tier multipliers (cheaper players change faster)
    PRICE_TIER_MULTIPLIERS = {
        (0.0, 5.0): 1.3,      # Budget players (£4.0-5.0m)
        (5.0, 7.0): 1.15,     # Mid-price (£5.0-7.0m)
        (7.0, 10.0): 1.0,     # Standard (£7.0-10.0m)
        (10.0, 15.0): 0.85,   # Premium (£10.0-15.0m)
    }

    def __init__(self, gameweek_data: GameweekData):
        self.data = gameweek_data
        self._price_change_cache = {}

    def _get_price_tier_multiplier(self, price: float) -> float:
        """
        Get multiplier based on price tier.
        Cheaper players typically change price faster due to lower thresholds.
        """
        for (min_price, max_price), multiplier in self.PRICE_TIER_MULTIPLIERS.items():
            if min_price <= price < max_price:
                return multiplier
        return 1.0

    def calculate_price_change_probability(
        self,
        player: Player,
        detailed: bool = False
    ) -> Dict:
        """
        Calculate probability and direction of price change.

        Returns:
            Dict with:
            - direction: 'RISE' | 'DROP' | 'STABLE'
            - probability: 'Very Likely' | 'Likely' | 'Possible' | 'Unlikely'
            - net_transfer_rate: Estimated net transfers per % owned
            - risk_level: 0-5 (0=stable, 5=imminent change)
        """
        # Use transfers_in_event and transfers_out_event from latest gameweek
        transfers_in = player.transfers_in_event
        transfers_out = player.transfers_out_event
        net_transfers = transfers_in - transfers_out

        # Calculate net transfer rate per % ownership
        # This normalizes for popularity (high-owned players need more transfers to change)
        ownership_pct = player.selected_by_percent
        if ownership_pct == 0:
            ownership_pct = 0.1  # Avoid division by zero

        net_transfer_rate = net_transfers / ownership_pct

        # Apply price tier multiplier
        price_multiplier = self._get_price_tier_multiplier(player.price)
        adjusted_rate = net_transfer_rate * price_multiplier

        # Determine direction and probability
        if adjusted_rate >= self.RISE_THRESHOLD_HIGH:
            direction = 'RISE'
            probability = 'Very Likely'
            risk_level = 5
        elif adjusted_rate >= self.RISE_THRESHOLD_MEDIUM:
            direction = 'RISE'
            probability = 'Likely'
            risk_level = 4
        elif adjusted_rate >= self.RISE_THRESHOLD_LOW:
            direction = 'RISE'
            probability = 'Possible'
            risk_level = 3
        elif adjusted_rate <= self.DROP_THRESHOLD_HIGH:
            direction = 'DROP'
            probability = 'Very Likely'
            risk_level = 5
        elif adjusted_rate <= self.DROP_THRESHOLD_MEDIUM:
            direction = 'DROP'
            probability = 'Likely'
            risk_level = 4
        elif adjusted_rate <= self.DROP_THRESHOLD_LOW:
            direction = 'DROP'
            probability = 'Possible'
            risk_level = 3
        else:
            direction = 'STABLE'
            probability = 'Unlikely'
            risk_level = 0

        result = {
            'direction': direction,
            'probability': probability,
            'risk_level': risk_level,
            'net_transfer_rate': round(adjusted_rate, 2),
        }

        if detailed:
            result.update({
                'transfers_in': transfers_in,
                'transfers_out': transfers_out,
                'net_transfers': net_transfers,
                'ownership_pct': ownership_pct,
                'price_multiplier': price_multiplier,
            })

        return result

    def get_price_change_warning(self, player: Player) -> Optional[str]:
        """
        Get human-readable warning about imminent price change.

        Returns:
            Warning string or None if stable
        """
        prediction = self.calculate_price_change_probability(player)

        if prediction['risk_level'] == 0:
            return None

        direction = prediction['direction']
        probability = prediction['probability']

        if direction == 'RISE':
            if probability == 'Very Likely':
                return f"⚠️ Very likely to RISE tonight (£{player.price}m → £{player.price + 0.1}m)"
            elif probability == 'Likely':
                return f"📈 Likely to RISE soon (£{player.price}m)"
            else:
                return f"↗️ Possible RISE (£{player.price}m)"

        elif direction == 'DROP':
            if probability == 'Very Likely':
                return f"⚠️ Very likely to DROP tonight (£{player.price}m → £{player.price - 0.1}m)"
            elif probability == 'Likely':
                return f"📉 Likely to DROP soon (£{player.price}m)"
            else:
                return f"↘️ Possible DROP (£{player.price}m)"

        return None

    def get_high_risk_price_changes(
        self,
        min_risk_level: int = 4
    ) -> Dict[str, List[Tuple[Player, Dict]]]:
        """
        Get all players at high risk of price change.

        Args:
            min_risk_level: Minimum risk level to include (1-5)

        Returns:
            Dict with 'risers' and 'fallers' lists
        """
        risers = []
        fallers = []

        for player in self.data.get_available_players():
            prediction = self.calculate_price_change_probability(player)

            if prediction['risk_level'] >= min_risk_level:
                if prediction['direction'] == 'RISE':
                    risers.append((player, prediction))
                elif prediction['direction'] == 'DROP':
                    fallers.append((player, prediction))

        # Sort by risk level (highest first)
        risers.sort(key=lambda x: x[1]['risk_level'], reverse=True)
        fallers.sort(key=lambda x: x[1]['risk_level'], reverse=True)

        return {
            'risers': risers[:20],  # Top 20 risers
            'fallers': fallers[:20],  # Top 20 fallers
        }

    def annotate_transfer_recommendations(
        self,
        transfer_recommendations: List[Dict]
    ) -> List[Dict]:
        """
        Add price change warnings to transfer recommendations.

        Args:
            transfer_recommendations: List of transfer dicts from TransferOptimizer

        Returns:
            Same list with added 'price_warning_in' and 'price_warning_out' fields
        """
        for rec in transfer_recommendations:
            # Check player being transferred IN
            player_in_id = rec['player_in'].get('id')
            if player_in_id:
                player_in = self.data.get_player_by_id(player_in_id)
                if player_in:
                    warning = self.get_price_change_warning(player_in)
                    if warning:
                        rec['price_warning_in'] = warning

            # Check player being transferred OUT
            player_out_id = rec['player_out'].get('id')
            if player_out_id:
                player_out = self.data.get_player_by_id(player_out_id)
                if player_out:
                    warning = self.get_price_change_warning(player_out)
                    if warning:
                        rec['price_warning_out'] = warning

        return transfer_recommendations

    def evaluate_squad_price_risk(
        self,
        squad_player_ids: List[int]
    ) -> Dict:
        """
        Evaluate price change risk for entire squad.

        Args:
            squad_player_ids: List of player IDs in current squad

        Returns:
            Dict with:
            - total_rise_potential: Expected value gain from risers
            - total_drop_risk: Expected value loss from fallers
            - high_risk_fallers: Players likely to drop
            - high_value_risers: Players likely to rise (locked in squad)
        """
        rise_potential = 0.0
        drop_risk = 0.0
        high_risk_fallers = []
        high_value_risers = []

        for player_id in squad_player_ids:
            player = self.data.get_player_by_id(player_id)
            if not player:
                continue

            prediction = self.calculate_price_change_probability(player)

            if prediction['direction'] == 'RISE' and prediction['risk_level'] >= 4:
                # Player likely to rise (locked value)
                rise_potential += 0.1  # £0.1m per rise
                high_value_risers.append({
                    'player': player.name,
                    'current_price': player.price,
                    'probability': prediction['probability']
                })

            elif prediction['direction'] == 'DROP' and prediction['risk_level'] >= 4:
                # Player likely to drop (lose selling value)
                drop_risk += 0.1  # £0.1m per drop
                high_risk_fallers.append({
                    'player': player.name,
                    'current_price': player.price,
                    'probability': prediction['probability'],
                    'warning': self.get_price_change_warning(player)
                })

        return {
            'total_rise_potential': round(rise_potential, 1),
            'total_drop_risk': round(drop_risk, 1),
            'net_value_change': round(rise_potential - drop_risk, 1),
            'high_risk_fallers': high_risk_fallers,
            'high_value_risers': high_value_risers,
        }

    def get_price_change_summary(self) -> Dict:
        """
        Get overall price change summary for all players.

        Returns:
            Dict with statistics about expected price changes
        """
        high_risk_changes = self.get_high_risk_price_changes(min_risk_level=4)

        return {
            'expected_risers_count': len(high_risk_changes['risers']),
            'expected_fallers_count': len(high_risk_changes['fallers']),
            'top_risers': [
                {
                    'name': p.name,
                    'team': self.data.get_team_by_id(p.team_id).short_name,
                    'price': p.price,
                    'ownership': p.selected_by_percent,
                    'probability': pred['probability']
                }
                for p, pred in high_risk_changes['risers'][:5]
            ],
            'top_fallers': [
                {
                    'name': p.name,
                    'team': self.data.get_team_by_id(p.team_id).short_name,
                    'price': p.price,
                    'ownership': p.selected_by_percent,
                    'probability': pred['probability']
                }
                for p, pred in high_risk_changes['fallers'][:5]
            ],
        }
