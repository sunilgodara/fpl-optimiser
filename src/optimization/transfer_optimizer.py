"""
Transfer planning optimizer with multi-week horizon.
Optimizes when to make transfers considering -4 point penalties.
"""
import pulp
from typing import Dict, List, Optional, Set, Tuple
from ..data.models import Player, GameweekData


class TransferOptimizer:
    """
    Optimizes transfer decisions over multiple gameweeks.

    Considers:
    - Free transfers (1 per week, can bank 1)
    - Transfer cost (-4 points per additional transfer)
    - Multi-week horizon for planning
    - Wildcard timing
    """

    TRANSFER_PENALTY = 4  # Points deducted per extra transfer
    MAX_FREE_TRANSFERS = 2  # Can bank max 1 transfer

    def __init__(self, gameweek_data: GameweekData):
        self.data = gameweek_data

    def calculate_transfer_value(
        self,
        player_out: Player,
        player_in: Player,
        expected_points: Dict[int, float],
        num_gameweeks: int = 3
    ) -> float:
        """
        Calculate the value of a transfer.

        Returns net points gained over N gameweeks minus transfer cost if applicable.
        """
        points_gained = expected_points.get(player_in.id, 0)
        points_lost = expected_points.get(player_out.id, 0)
        net_points = points_gained - points_lost

        return net_points

    def suggest_transfers(
        self,
        current_squad: List[int],
        expected_points: Dict[int, float],
        free_transfers: int = 1,
        budget_remaining: float = 0.0,
        num_transfers: int = 1,
        num_gameweeks: int = 3
    ) -> Optional[Dict]:
        """
        Suggest best transfers for current gameweek.

        Args:
            current_squad: List of current player IDs
            expected_points: Expected points per player over horizon
            free_transfers: Number of free transfers available (1 or 2)
            budget_remaining: Budget available (in millions)
            num_transfers: Number of transfers to suggest
            num_gameweeks: Horizon for expected points

        Returns:
            Dict with transfer suggestions or None
        """
        squad_players = [self.data.get_player_by_id(pid) for pid in current_squad]
        available_players = self.data.get_available_players()

        # Players not in squad
        potential_transfers_in = [
            p for p in available_players
            if p.id not in current_squad
        ]

        best_transfers = []

        for player_out in squad_players:
            for player_in in potential_transfers_in:
                # Check position match
                if player_out.position != player_in.position:
                    continue

                # Check budget
                price_diff = player_in.price - player_out.price
                if price_diff > budget_remaining:
                    continue

                # Check team constraint (won't violate max 3 per team)
                squad_team_count = sum(1 for p in squad_players if p.team_id == player_in.team_id)
                if player_out.team_id != player_in.team_id and squad_team_count >= 3:
                    continue

                # Calculate value
                value = self.calculate_transfer_value(
                    player_out, player_in, expected_points, num_gameweeks
                )

                best_transfers.append({
                    'player_out': player_out,
                    'player_in': player_in,
                    'value': value,
                    'price_diff': price_diff,
                    'ep_out': expected_points.get(player_out.id, 0),
                    'ep_in': expected_points.get(player_in.id, 0),
                })

        # Sort by value
        best_transfers.sort(key=lambda x: x['value'], reverse=True)

        if not best_transfers:
            return None

        # Select top N transfers
        selected_transfers = best_transfers[:num_transfers]

        # Calculate if transfers are worth it
        total_value = sum(t['value'] for t in selected_transfers)
        transfer_cost = max(0, num_transfers - free_transfers) * self.TRANSFER_PENALTY
        net_value = total_value - transfer_cost

        return {
            'transfers': selected_transfers,
            'total_value': total_value,
            'transfer_cost': transfer_cost,
            'net_value': net_value,
            'recommended': net_value > 0,  # Only recommend if positive value
        }

    def optimize_multi_week_transfers(
        self,
        current_squad: List[int],
        expected_points_by_week: Dict[int, Dict[int, float]],  # {gw: {player_id: points}}
        free_transfers: int = 1,
        budget_remaining: float = 0.0,
        planning_horizon: int = 5,
        use_wildcard_gw: Optional[int] = None
    ) -> Dict:
        """
        Optimize transfers over multiple gameweeks.

        Args:
            current_squad: Current squad player IDs
            expected_points_by_week: Expected points for each player per gameweek
            free_transfers: Current free transfers available
            budget_remaining: Budget available
            planning_horizon: Number of gameweeks to plan
            use_wildcard_gw: Gameweek to use wildcard (None = don't use)

        Returns:
            Transfer plan for each gameweek
        """
        # Determine starting gameweek from expected_points_by_week keys
        # (This handles cases where we're planning for next GW, not current)
        if expected_points_by_week:
            start_gw = min(expected_points_by_week.keys())
        else:
            start_gw = self.data.current_gameweek

        transfer_plan = {}

        working_squad = current_squad.copy()
        working_free_transfers = free_transfers
        working_budget = budget_remaining

        for gw_offset in range(planning_horizon):
            gw = start_gw + gw_offset

            # Check if wildcard gameweek
            if use_wildcard_gw and gw == use_wildcard_gw:
                transfer_plan[gw] = {
                    'action': 'WILDCARD',
                    'transfers': [],
                    'message': 'Wildcard active - rebuild entire squad'
                }
                working_free_transfers = 1  # Reset after wildcard
                continue

            # Get expected points for this gameweek + next 2
            horizon_points = {}
            for player_id in self.data.get_available_players():
                total_ep = 0
                for future_gw in range(gw, min(gw + 3, start_gw + planning_horizon)):
                    if future_gw in expected_points_by_week:
                        total_ep += expected_points_by_week[future_gw].get(player_id.id, 0)
                horizon_points[player_id.id] = total_ep

            # Suggest transfers
            # For first gameweek, use all available free transfers (up to max 5)
            # For subsequent gameweeks, use 1 transfer per week
            num_transfers_to_make = min(working_free_transfers, 5) if gw_offset == 0 else 1

            suggestion = self.suggest_transfers(
                working_squad,
                horizon_points,
                working_free_transfers,
                working_budget,
                num_transfers=num_transfers_to_make,
                num_gameweeks=3
            )

            if suggestion and suggestion['recommended']:
                # Apply all suggested transfers
                transfers_made = []
                for transfer in suggestion['transfers']:
                    # Apply transfer
                    working_squad.remove(transfer['player_out'].id)
                    working_squad.append(transfer['player_in'].id)
                    working_budget -= transfer['price_diff']

                    transfers_made.append({
                        'out': transfer['player_out'].name,
                        'in': transfer['player_in'].name,
                        'value': transfer['value'],
                    })

                # Update free transfers
                num_transfers_made = len(suggestion['transfers'])
                working_free_transfers = max(0, working_free_transfers - num_transfers_made)

                transfer_plan[gw] = {
                    'action': 'TRANSFER',
                    'transfers': transfers_made,
                    'free_transfers_used': min(num_transfers_made, free_transfers if gw_offset == 0 else working_free_transfers + num_transfers_made),
                    'points_hit': suggestion['transfer_cost'],
                    'expected_gain': suggestion['net_value']
                }
            else:
                transfer_plan[gw] = {
                    'action': 'NO_TRANSFER',
                    'transfers': [],
                    'message': 'No valuable transfers available - bank transfer'
                }
                # Bank free transfer (max 2)
                working_free_transfers = min(working_free_transfers + 1, self.MAX_FREE_TRANSFERS)

        return transfer_plan

    def evaluate_wildcard_timing(
        self,
        current_squad: List[int],
        expected_points_by_week: Dict[int, Dict[int, float]],
        budget_remaining: float,
        gameweeks_to_consider: List[int]
    ) -> Dict[int, float]:
        """
        Evaluate the value of using wildcard in different gameweeks.

        Returns:
            Dict mapping gameweek -> expected value of using wildcard
        """
        from .squad_optimizer import SquadOptimizer

        wildcard_values = {}

        for gw in gameweeks_to_consider:
            # Calculate expected points for next 5 weeks after wildcard
            horizon_points = {}
            for player in self.data.get_available_players():
                total_ep = 0
                for future_gw in range(gw, gw + 5):
                    if future_gw in expected_points_by_week:
                        total_ep += expected_points_by_week[future_gw].get(player.id, 0)
                horizon_points[player.id] = total_ep

            # Optimize new squad with wildcard
            optimizer = SquadOptimizer(self.data)
            optimal_squad = optimizer.optimize_squad(horizon_points, verbose=False)

            if optimal_squad:
                # Compare to current squad expected points
                current_squad_ep = sum(
                    horizon_points.get(pid, 0) for pid in current_squad
                )

                # Value is difference (accounting for fact we get best 11 from 15)
                wildcard_value = optimal_squad['total_expected_points'] - current_squad_ep * 0.85
                wildcard_values[gw] = wildcard_value
            else:
                wildcard_values[gw] = 0

        return wildcard_values

    def get_transfer_recommendations(
        self,
        current_squad: List[int],
        expected_points: Dict[int, float],
        free_transfers: int = 1,
        budget_remaining: float = 0.0,
        max_suggestions: int = 5
    ) -> List[Dict]:
        """
        Get top transfer recommendations with reasoning.

        Returns list of transfer options ranked by value.
        """
        # Use all available free transfers (up to max 5)
        num_transfers_to_suggest = min(free_transfers, 5)

        suggestion = self.suggest_transfers(
            current_squad,
            expected_points,
            free_transfers,
            budget_remaining,
            num_transfers=num_transfers_to_suggest,
            num_gameweeks=3
        )

        if not suggestion:
            return []

        recommendations = []

        for i, transfer in enumerate(suggestion['transfers'][:max_suggestions]):
            player_out = transfer['player_out']
            player_in = transfer['player_in']

            team_out = self.data.get_team_by_id(player_out.team_id)
            team_in = self.data.get_team_by_id(player_in.team_id)

            # Determine reasoning
            reasons = []
            if transfer['ep_in'] > transfer['ep_out'] * 1.5:
                reasons.append("Significant fixture swing")
            if player_in.form > player_out.form * 1.3:
                reasons.append("Much better form")
            if player_out.chance_of_playing_next_round and player_out.chance_of_playing_next_round < 75:
                reasons.append("Current player injury concern")
            if transfer['price_diff'] < -1.0:
                reasons.append("Downgrade to fund other moves")

            recommendations.append({
                'rank': i + 1,
                'player_out': {
                    'name': player_out.name,
                    'team': team_out.short_name,
                    'price': player_out.price,
                    'expected_points': transfer['ep_out']
                },
                'player_in': {
                    'name': player_in.name,
                    'team': team_in.short_name,
                    'price': player_in.price,
                    'expected_points': transfer['ep_in']
                },
                'value': transfer['value'],
                'price_change': transfer['price_diff'],
                'reasons': reasons if reasons else ["Better expected points"],
                'worth_hit': transfer['value'] > 4.5  # Worth -4 if gain > 4.5 points
            })

        return recommendations
