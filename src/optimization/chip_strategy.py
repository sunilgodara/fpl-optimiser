"""
Chip strategy optimizer for Wildcard, Bench Boost, Triple Captain, and Free Hit.
"""
from typing import Dict, List, Optional, Tuple
from ..data.models import Player, GameweekData, Fixture
from .squad_optimizer import SquadOptimizer


class ChipStrategyOptimizer:
    """
    Optimizes usage of FPL chips:
    - Wildcard (2 per season): Unlimited free transfers
    - Bench Boost: Bench players score points
    - Triple Captain: Captain gets 3x points instead of 2x
    - Free Hit: Make unlimited transfers for 1 week, then revert
    """

    def __init__(self, gameweek_data: GameweekData):
        self.data = gameweek_data

    def _count_fixtures_in_gameweek(self, team_id: int, gameweek: int) -> int:
        """Count number of fixtures a team has in a gameweek."""
        count = 0
        for fixture in self.data.fixtures:
            if fixture.event == gameweek:
                if fixture.team_h == team_id or fixture.team_a == team_id:
                    count += 1
        return count

    def _get_double_gameweeks(self, horizon: int = 10) -> Dict[int, List[int]]:
        """
        Identify double gameweeks (teams playing twice).

        Returns:
            Dict mapping gameweek -> list of team_ids with double fixtures
        """
        current_gw = self.data.current_gameweek
        double_gameweeks = {}

        for gw in range(current_gw, current_gw + horizon):
            teams_with_doubles = []
            for team_id in self.data.teams.keys():
                fixture_count = self._count_fixtures_in_gameweek(team_id, gw)
                if fixture_count >= 2:
                    teams_with_doubles.append(team_id)

            if teams_with_doubles:
                double_gameweeks[gw] = teams_with_doubles

        return double_gameweeks

    def _get_blank_gameweeks(self, horizon: int = 10) -> Dict[int, List[int]]:
        """
        Identify blank gameweeks (teams not playing).

        Returns:
            Dict mapping gameweek -> list of team_ids with no fixtures
        """
        current_gw = self.data.current_gameweek
        blank_gameweeks = {}

        for gw in range(current_gw, current_gw + horizon):
            teams_with_blanks = []
            for team_id in self.data.teams.keys():
                fixture_count = self._count_fixtures_in_gameweek(team_id, gw)
                if fixture_count == 0:
                    teams_with_blanks.append(team_id)

            if teams_with_blanks:
                blank_gameweeks[gw] = teams_with_blanks

        return blank_gameweeks

    def evaluate_wildcard_opportunities(
        self,
        current_squad: List[int],
        expected_points_by_week: Dict[int, Dict[int, float]],
        horizon: int = 10
    ) -> Dict[int, Dict]:
        """
        Evaluate best gameweeks to use wildcard.

        Wildcard is valuable when:
        1. Many players need changing (injuries, poor form)
        2. Before a double gameweek to load up on those teams
        3. After a blank gameweek to restructure
        4. Mid-season to catch price rises and form changes

        Returns:
            Dict mapping gameweek -> evaluation metrics
        """
        # Determine starting gameweek from expected_points_by_week
        if expected_points_by_week:
            start_gw = min(expected_points_by_week.keys())
        else:
            start_gw = self.data.current_gameweek

        double_gameweeks = self._get_double_gameweeks(horizon)
        wildcard_evaluations = {}

        for gw in range(start_gw, start_gw + horizon):
            # Calculate squad health (% of players performing well)
            squad_players = [self.data.get_player_by_id(pid) for pid in current_squad]
            healthy_count = sum(1 for p in squad_players if p.is_available())
            squad_health = healthy_count / len(squad_players)

            # Calculate potential points gain
            # Compare current squad vs optimal squad for next 5 weeks
            horizon_points = {}
            for player in self.data.get_available_players():
                total_ep = 0
                for future_gw in range(gw, min(gw + 5, start_gw + horizon)):
                    if future_gw in expected_points_by_week:
                        total_ep += expected_points_by_week[future_gw].get(player.id, 0)
                horizon_points[player.id] = total_ep

            optimizer = SquadOptimizer(self.data)
            optimal = optimizer.optimize_squad(horizon_points, verbose=False)

            if optimal:
                current_squad_ep = sum(horizon_points.get(pid, 0) for pid in current_squad)
                potential_gain = optimal['total_expected_points'] - current_squad_ep * 0.85

                # Bonus value if double gameweek is coming
                dgw_bonus = 0
                if gw + 1 in double_gameweeks or gw + 2 in double_gameweeks:
                    dgw_bonus = 20  # Significant bonus for timing before DGW

                # Calculate number of transfers needed without wildcard
                current_set = set(current_squad)
                optimal_set = set(optimal['squad'])
                transfers_needed = len(current_set - optimal_set)

                # Wildcard value
                # If you need 5+ transfers, wildcard saves (transfers_needed - 1) * 4 points
                transfer_savings = max(0, (transfers_needed - 1) * 4)

                total_value = potential_gain + dgw_bonus + transfer_savings * 0.5

                wildcard_evaluations[gw] = {
                    'total_value': total_value,
                    'potential_gain': potential_gain,
                    'squad_health': squad_health,
                    'transfers_needed': transfers_needed,
                    'transfer_savings': transfer_savings,
                    'dgw_bonus': dgw_bonus,
                    'is_dgw_week': gw in double_gameweeks,
                    'recommended': total_value > 30,  # Recommend if value > 30 points
                }

        return wildcard_evaluations

    def evaluate_bench_boost(
        self,
        squad: List[int],
        expected_points: Dict[int, float],
        horizon: int = 10,
        start_gw: Optional[int] = None
    ) -> Dict[int, Dict]:
        """
        Evaluate best gameweeks to use Bench Boost.

        Bench Boost is valuable when:
        1. All 15 players have good fixtures (double gameweeks!)
        2. Bench players are strong and likely to play
        3. Multiple teams have double fixtures

        Returns:
            Dict mapping gameweek -> evaluation
        """
        if start_gw is None:
            start_gw = self.data.current_gameweek

        double_gameweeks = self._get_double_gameweeks(horizon)
        evaluations = {}

        squad_players = [self.data.get_player_by_id(pid) for pid in squad]

        for gw in range(start_gw, start_gw + horizon):
            # Count how many squad players have double gameweeks
            dgw_count = 0
            for player in squad_players:
                if gw in double_gameweeks and player.team_id in double_gameweeks[gw]:
                    dgw_count += 1

            # Expected points from bench (assume worst 4 players)
            sorted_by_ep = sorted(
                squad_players,
                key=lambda p: expected_points.get(p.id, 0)
            )
            bench_players = sorted_by_ep[:4]  # Bottom 4 = bench
            bench_ep = sum(expected_points.get(p.id, 0) for p in bench_players)

            # Check if bench players will actually play
            bench_reliability = sum(
                1 for p in bench_players
                if p.minutes > 500  # Played regularly this season
            ) / 4

            # Total value
            value = bench_ep * bench_reliability

            # Bonus for double gameweek
            if dgw_count >= 8:  # At least 8 players in DGW
                value *= 1.5

            evaluations[gw] = {
                'value': value,
                'bench_expected_points': bench_ep,
                'bench_reliability': bench_reliability,
                'dgw_player_count': dgw_count,
                'is_double_gameweek': dgw_count >= 8,
                'recommended': value > 15 and dgw_count >= 8,  # Use in DGW with strong bench
            }

        return evaluations

    def evaluate_triple_captain(
        self,
        expected_points: Dict[int, float],
        horizon: int = 10,
        start_gw: Optional[int] = None
    ) -> Dict[int, Dict]:
        """
        Evaluate best gameweeks to use Triple Captain.

        Triple Captain is valuable when:
        1. Top player has double gameweek
        2. Top player has very easy fixture
        3. Maximum differential between captain and other players

        Returns:
            Dict mapping gameweek -> evaluation with best captain choice
        """
        if start_gw is None:
            start_gw = self.data.current_gameweek

        double_gameweeks = self._get_double_gameweeks(horizon)
        evaluations = {}

        for gw in range(start_gw, start_gw + horizon):
            # Find best captain option for this gameweek
            best_captain = None
            best_ep = 0

            for player in self.data.get_available_players():
                ep = expected_points.get(player.id, 0)

                # Bonus for double gameweek
                if gw in double_gameweeks and player.team_id in double_gameweeks[gw]:
                    ep *= 1.8  # Huge bonus for DGW

                if ep > best_ep:
                    best_ep = ep
                    best_captain = player

            if best_captain:
                # Triple captain value = 2x captain points (you get 3x instead of 1x)
                tc_value = best_ep * 2  # Extra 2x on top of normal 1x

                # Normal captain in same gameweek would give 1x bonus
                normal_captain_bonus = best_ep

                # Net gain from TC vs normal captain
                net_gain = tc_value - normal_captain_bonus

                has_dgw = (
                    gw in double_gameweeks and
                    best_captain.team_id in double_gameweeks[gw]
                )

                evaluations[gw] = {
                    'value': net_gain,
                    'captain_name': best_captain.name,
                    'captain_id': best_captain.id,
                    'captain_team': self.data.get_team_by_id(best_captain.team_id).short_name,
                    'captain_expected_points': best_ep,
                    'has_double_gameweek': has_dgw,
                    'recommended': net_gain > 20 or has_dgw,  # Use in DGW or huge fixture
                }

        return evaluations

    def evaluate_free_hit(
        self,
        current_squad: List[int],
        expected_points_by_week: Dict[int, Dict[int, float]],
        horizon: int = 10
    ) -> Dict[int, Dict]:
        """
        Evaluate best gameweeks to use Free Hit.

        Free Hit is valuable when:
        1. Major blank gameweek (many teams not playing)
        2. Your team has many blanks but one-week opportunity
        3. Unique double gameweek where you can't fit all good players

        Returns:
            Dict mapping gameweek -> evaluation
        """
        # Determine starting gameweek from expected_points_by_week
        if expected_points_by_week:
            start_gw = min(expected_points_by_week.keys())
        else:
            start_gw = self.data.current_gameweek

        blank_gameweeks = self._get_blank_gameweeks(horizon)
        double_gameweeks = self._get_double_gameweeks(horizon)
        evaluations = {}

        squad_players = [self.data.get_player_by_id(pid) for pid in current_squad]

        for gw in range(start_gw, start_gw + horizon):
            # Count squad players affected by blanks
            blank_count = 0
            if gw in blank_gameweeks:
                for player in squad_players:
                    if player.team_id in blank_gameweeks[gw]:
                        blank_count += 1

            # Get optimal squad for just this gameweek
            gw_points = expected_points_by_week.get(gw, {})
            optimizer = SquadOptimizer(self.data)
            optimal = optimizer.optimize_squad(gw_points, verbose=False)

            if optimal:
                # Compare optimal vs current squad
                current_squad_ep = sum(gw_points.get(pid, 0) for pid in current_squad) * 0.73  # Best 11 of 15
                optimal_ep = optimal['total_expected_points'] * 0.73

                gain = optimal_ep - current_squad_ep

                # Higher value if it's a blank gameweek
                if blank_count >= 5:
                    gain *= 1.5

                evaluations[gw] = {
                    'value': gain,
                    'current_squad_ep': current_squad_ep,
                    'optimal_squad_ep': optimal_ep,
                    'blank_player_count': blank_count,
                    'is_blank_gameweek': blank_count >= 5,
                    'is_double_gameweek': gw in double_gameweeks,
                    'recommended': gain > 25 and blank_count >= 5,  # Use in blank GW with big gain
                }

        return evaluations

    def resolve_chip_conflicts(
        self,
        chip_recommendations: Dict[str, Dict]
    ) -> Dict[str, Dict]:
        """
        Resolve conflicts where multiple chips are recommended for the same gameweek.
        FPL only allows one chip per gameweek.

        Args:
            chip_recommendations: Dict with chip recommendations from get_chip_strategy

        Returns:
            Resolved recommendations with at most one chip per gameweek
        """
        # Build a mapping of gameweek -> list of (chip_name, value, data)
        gw_to_chips = {}

        for chip_name, chip_data in chip_recommendations.items():
            best_gw = chip_data['best_gameweek']
            best_value = chip_data['best_value']

            if best_gw not in gw_to_chips:
                gw_to_chips[best_gw] = []

            gw_to_chips[best_gw].append({
                'chip_name': chip_name,
                'value': best_value,
                'data': chip_data
            })

        # Resolve conflicts: pick highest value chip for each gameweek
        resolved_recommendations = {}
        used_gameweeks = set()
        rejected_chips = []  # Chips that lost conflict resolution

        # Sort chips by value (highest first) to prioritize best chips
        all_chips = []
        for chip_name, chip_data in chip_recommendations.items():
            all_chips.append({
                'chip_name': chip_name,
                'best_gw': chip_data['best_gameweek'],
                'value': chip_data['best_value'],
                'data': chip_data
            })
        all_chips.sort(key=lambda x: x['value'], reverse=True)

        # Assign chips to gameweeks (highest value first)
        for chip in all_chips:
            chip_name = chip['chip_name']
            best_gw = chip['best_gw']

            if best_gw in used_gameweeks:
                # Conflict: try to find alternative gameweek for this chip
                evaluations = chip['data']['evaluations']
                alternative_found = False

                # Sort gameweeks by value
                sorted_gws = sorted(
                    evaluations.items(),
                    key=lambda x: x[1].get('value' if chip_name != 'wildcard' else 'total_value', 0),
                    reverse=True
                )

                for alt_gw, alt_eval in sorted_gws:
                    if alt_gw not in used_gameweeks:
                        # Found alternative gameweek
                        resolved_recommendations[chip_name] = {
                            **chip['data'],
                            'best_gameweek': alt_gw,
                            'best_value': alt_eval.get('value' if chip_name != 'wildcard' else 'total_value', 0),
                            'conflict_resolution': f"Moved from GW{best_gw} (conflict with higher-value chip)",
                            'original_gameweek': best_gw
                        }
                        used_gameweeks.add(alt_gw)
                        alternative_found = True
                        break

                if not alternative_found:
                    # No alternative found, chip is rejected
                    rejected_chips.append({
                        'chip_name': chip_name,
                        'original_gw': best_gw,
                        'value': chip['value']
                    })
            else:
                # No conflict, use original recommendation
                resolved_recommendations[chip_name] = chip['data']
                used_gameweeks.add(best_gw)

        # Add metadata about conflicts
        if rejected_chips:
            resolved_recommendations['_conflicts'] = {
                'rejected_chips': rejected_chips,
                'message': 'Some chips could not be scheduled due to gameweek conflicts'
            }

        return resolved_recommendations

    def get_chip_strategy(
        self,
        current_squad: List[int],
        expected_points_by_week: Dict[int, Dict[int, float]],
        available_chips: List[str],
        horizon: int = 10
    ) -> Dict[str, Dict]:
        """
        Get comprehensive chip strategy recommendation.

        Args:
            current_squad: Current squad player IDs
            expected_points_by_week: Expected points per player per gameweek
            available_chips: List of chips still available (e.g., ['wildcard', 'bench_boost'])
            horizon: Weeks to plan ahead

        Returns:
            Dict with recommendations for each chip type
        """
        recommendations = {}

        # Determine starting gameweek from expected_points_by_week
        if expected_points_by_week:
            start_gw = min(expected_points_by_week.keys())
        else:
            start_gw = self.data.current_gameweek

        # Aggregate expected points for multi-week evaluations
        total_expected_points = {}
        for player in self.data.get_available_players():
            total_ep = sum(
                expected_points_by_week.get(gw, {}).get(player.id, 0)
                for gw in range(start_gw, start_gw + horizon)
            )
            total_expected_points[player.id] = total_ep

        # Evaluate each chip type
        if 'wildcard' in available_chips or 'wildcard1' in available_chips or 'wildcard2' in available_chips:
            wc_eval = self.evaluate_wildcard_opportunities(
                current_squad, expected_points_by_week, horizon
            )
            best_wc_gw = max(wc_eval.items(), key=lambda x: x[1]['total_value'])
            recommendations['wildcard'] = {
                'evaluations': wc_eval,
                'best_gameweek': best_wc_gw[0],
                'best_value': best_wc_gw[1]['total_value'],
                'recommended': best_wc_gw[1]['recommended']
            }

        if 'bboost' in available_chips:
            bb_eval = self.evaluate_bench_boost(
                current_squad, total_expected_points, horizon, start_gw
            )
            best_bb_gw = max(bb_eval.items(), key=lambda x: x[1]['value'])
            recommendations['bench_boost'] = {
                'evaluations': bb_eval,
                'best_gameweek': best_bb_gw[0],
                'best_value': best_bb_gw[1]['value'],
                'recommended': best_bb_gw[1]['recommended']
            }

        if '3xc' in available_chips:
            tc_eval = self.evaluate_triple_captain(total_expected_points, horizon, start_gw)
            best_tc_gw = max(tc_eval.items(), key=lambda x: x[1]['value'])
            recommendations['triple_captain'] = {
                'evaluations': tc_eval,
                'best_gameweek': best_tc_gw[0],
                'best_captain': best_tc_gw[1]['captain_name'],
                'best_value': best_tc_gw[1]['value'],
                'recommended': best_tc_gw[1]['recommended']
            }

        if 'freehit' in available_chips:
            fh_eval = self.evaluate_free_hit(
                current_squad, expected_points_by_week, horizon
            )
            best_fh_gw = max(fh_eval.items(), key=lambda x: x[1]['value'])
            recommendations['free_hit'] = {
                'evaluations': fh_eval,
                'best_gameweek': best_fh_gw[0],
                'best_value': best_fh_gw[1]['value'],
                'recommended': best_fh_gw[1]['recommended']
            }

        # Resolve conflicts: only one chip per gameweek allowed
        resolved_recommendations = self.resolve_chip_conflicts(recommendations)

        return resolved_recommendations
