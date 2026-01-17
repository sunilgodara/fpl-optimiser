"""
Bonus Points System (BPS) predictor for FPL.

Predicts bonus points (3/2/1 for top 3 BPS in each match) using Opta's
official BPS formula with 2025/26 season rule updates.
"""
from typing import Dict, Optional, Tuple
from ..data.models import Player, Team, Fixture, GameweekData
import statistics


class BonusPointsPredictor:
    """
    Predicts FPL bonus points using the official BPS (Bonus Points System) formula.

    2025/26 Season Updates:
    - Penalties now worth 12 BPS (regardless of position) - CHANGED
    - Defenders get +2 FPL points for 10+ CBIT (Clearances, Blocks, Interceptions, Tackles)
    - Midfielders/Forwards get +2 FPL points for 12+ CBIRT (includes Recoveries)

    Top 3 BPS in each match get bonus FPL points:
    - 1st place: 3 points
    - 2nd place: 2 points
    - 3rd place: 1 point
    """

    # BPS scoring (Official Opta formula)
    BPS_SCORING = {
        # Goals (position-dependent)
        'goal': {'FWD': 24, 'MID': 18, 'DEF': 12, 'GK': 12},

        # Assists (all positions)
        'assist': 9,

        # Penalties (NEW 2025/26: same for all positions)
        'penalty': 12,

        # Clean sheets (60+ minutes)
        'clean_sheet': {'GK': 12, 'DEF': 12, 'MID': 6, 'FWD': 0},

        # Defensive actions (per action)
        'clearance': 1,
        'block': 1,
        'interception': 1,
        'tackle': 1,
        'recovery': 1,

        # Attacking actions
        'key_pass': 1,
        'shot_on_target': 2,
        'big_chance_created': 3,

        # Goalkeeping
        'save': 2,
        'penalty_save': 15,

        # Penalties (negative)
        'yellow_card': -3,
        'red_card': -9,
        'own_goal': -6,
        'missing_big_chance': -3,
        'concede_penalty': -3,
        'error_leading_to_goal': -3,
    }

    # Player archetypes (historical patterns)
    # Based on BPS per 90 minutes for different player types
    ARCHETYPE_BPS_PER_90 = {
        'GK': {
            'sweeper_keeper': 28,  # High saves, good distribution
            'shot_stopper': 32,    # Very high saves
            'average': 24,
        },
        'DEF': {
            'attacking_fullback': 26,  # Wing-backs with attacking returns
            'defensive_rock': 28,      # High CBIT, clean sheets
            'ball_playing': 24,        # Good passing, moderate defense
            'average': 22,
        },
        'MID': {
            'creator': 26,         # High key passes, assists
            'goal_scorer': 28,     # Goals + some assists
            'box_to_box': 24,      # Balanced contributions
            'defensive': 20,       # Tackles, interceptions
            'average': 22,
        },
        'FWD': {
            'poacher': 28,         # High goals, low involvement
            'target_man': 26,      # Goals + assists + hold-up
            'pressing': 24,        # Goals + defensive work
            'average': 24,
        },
    }

    def __init__(self, gameweek_data: GameweekData, api_client):
        self.data = gameweek_data
        self.api_client = api_client
        self._player_cache = {}

    def _get_player_archetype(self, player: Player) -> str:
        """
        Determine player archetype based on stats.

        This helps predict BPS patterns.
        """
        # Simplified archetype detection
        # In production, would use detailed historical analysis

        if player.position == 'GK':
            # Goalkeepers - check saves per game
            return 'average'  # Default for now

        elif player.position == 'DEF':
            # Defenders - check attacking returns vs defensive focus
            if player.points_per_game > 4.5:
                return 'attacking_fullback'
            elif player.clean_sheets > 5:
                return 'defensive_rock'
            else:
                return 'average'

        elif player.position == 'MID':
            # Midfielders - check goals vs assists ratio
            goals = getattr(player, 'goals_scored', 0)
            assists = getattr(player, 'assists', 0)

            if goals > assists * 1.5:
                return 'goal_scorer'
            elif assists > goals * 1.5:
                return 'creator'
            else:
                return 'average'

        else:  # FWD
            # Forwards - mostly similar patterns
            return 'average'

    def predict_bps(
        self,
        player: Player,
        fixture: Fixture,
        minutes_expected: float = 90,
        predicted_goals: float = 0.0,
        predicted_assists: float = 0.0,
        clean_sheet_prob: float = 0.0
    ) -> float:
        """
        Predict BPS for a player in a fixture.

        Args:
            player: Player object
            fixture: Fixture object
            minutes_expected: Expected minutes (default 90)
            predicted_goals: Expected goals (from xG model)
            predicted_assists: Expected assists (from xA model)
            clean_sheet_prob: Probability of clean sheet (0-1)

        Returns:
            Expected BPS
        """
        if minutes_expected < 60:
            # Players playing < 60 mins rarely get bonus
            return 0.0

        bps = 0.0

        # 1. Goal contribution
        goal_bps = self.BPS_SCORING['goal'][player.position]
        bps += predicted_goals * goal_bps

        # 2. Assist contribution
        bps += predicted_assists * self.BPS_SCORING['assist']

        # 3. Clean sheet contribution (if 60+ mins)
        cs_bps = self.BPS_SCORING['clean_sheet'][player.position]
        bps += clean_sheet_prob * cs_bps

        # 4. Position-specific contributions
        archetype = self._get_player_archetype(player)

        if player.position == 'GK':
            bps += self._predict_gk_bps(player, fixture, minutes_expected)

        elif player.position == 'DEF':
            bps += self._predict_def_bps(player, fixture, minutes_expected)

        elif player.position == 'MID':
            bps += self._predict_mid_bps(player, fixture, minutes_expected)

        else:  # FWD
            bps += self._predict_fwd_bps(player, fixture, minutes_expected)

        return max(0, bps)

    def _predict_gk_bps(
        self,
        player: Player,
        fixture: Fixture,
        minutes_expected: float
    ) -> float:
        """Predict GK-specific BPS contributions."""
        bps = 0.0

        # Estimate saves based on opponent strength
        opponent_id = fixture.team_a if fixture.team_h == player.team_id else fixture.team_h
        opponent = self.data.get_team_by_id(opponent_id)

        if opponent:
            # Stronger opponents = more shots = more saves
            expected_saves = 3.0 if opponent.strength_attack_away > 1200 else 2.0
            bps += expected_saves * self.BPS_SCORING['save']

        return bps

    def _predict_def_bps(
        self,
        player: Player,
        fixture: Fixture,
        minutes_expected: float
    ) -> float:
        """
        Predict DEF-specific BPS contributions.

        NEW 2025/26: Defenders get +2 FPL points for 10+ CBIT.
        This doesn't directly affect BPS, but indicates high defensive activity.
        """
        bps = 0.0

        # Estimate CBIT (Clearances, Blocks, Interceptions, Tackles)
        # Based on opponent strength and player archetype
        opponent_id = fixture.team_a if fixture.team_h == player.team_id else fixture.team_h
        opponent = self.data.get_team_by_id(opponent_id)

        if opponent:
            # Stronger opponents = more defensive work
            base_cbit = 8.0 if opponent.strength_attack_away > 1200 else 6.0

            # Each CBIT action = ~1-2 BPS
            # Average across clearances, blocks, interceptions, tackles
            cbit_bps = base_cbit * 1.5
            bps += cbit_bps

        # Attacking fullbacks get some attacking stats
        archetype = self._get_player_archetype(player)
        if archetype == 'attacking_fullback':
            # Key passes, shots on target
            bps += 0.5 * self.BPS_SCORING['key_pass']
            bps += 0.3 * self.BPS_SCORING['shot_on_target']

        return bps

    def _predict_mid_bps(
        self,
        player: Player,
        fixture: Fixture,
        minutes_expected: float
    ) -> float:
        """
        Predict MID-specific BPS contributions.

        NEW 2025/26: Mids get +2 FPL points for 12+ CBIRT (includes recoveries).
        """
        bps = 0.0

        archetype = self._get_player_archetype(player)

        if archetype == 'creator':
            # High key passes
            expected_key_passes = 2.0
            bps += expected_key_passes * self.BPS_SCORING['key_pass']

        elif archetype == 'goal_scorer':
            # Shots on target
            expected_shots = 2.0
            bps += expected_shots * self.BPS_SCORING['shot_on_target']

        elif archetype == 'defensive':
            # Tackles, interceptions, recoveries
            expected_defensive = 6.0
            bps += expected_defensive * 1.0  # ~1 BPS per action

        else:  # box_to_box or average
            # Balanced contributions
            bps += 1.0 * self.BPS_SCORING['key_pass']
            bps += 0.5 * self.BPS_SCORING['shot_on_target']

        return bps

    def _predict_fwd_bps(
        self,
        player: Player,
        fixture: Fixture,
        minutes_expected: float
    ) -> float:
        """Predict FWD-specific BPS contributions."""
        bps = 0.0

        # Forwards primarily get BPS from goals/assists already counted
        # Add some shots on target
        expected_shots = 2.0
        bps += expected_shots * self.BPS_SCORING['shot_on_target']

        # Target men may have some key passes
        archetype = self._get_player_archetype(player)
        if archetype == 'target_man':
            bps += 0.5 * self.BPS_SCORING['key_pass']

        return bps

    def predict_bonus_points(
        self,
        player: Player,
        fixture: Fixture,
        predicted_bps: float,
        teammates_bps: Optional[Dict[int, float]] = None
    ) -> float:
        """
        Convert BPS to actual bonus FPL points (3/2/1).

        Top 3 BPS in match get bonus points.

        Args:
            player: Player object
            fixture: Fixture object
            predicted_bps: Predicted BPS for this player
            teammates_bps: Optional dict of {player_id: bps} for team context

        Returns:
            Expected bonus points (0-3, can be fractional for probability)
        """
        # Simplified: Estimate probability of top 3 finish
        # In production, would simulate full match with all 22 players

        if predicted_bps < 20:
            # Very unlikely to get bonus with < 20 BPS
            return 0.0

        elif predicted_bps < 30:
            # Low chance, maybe 1 point
            return 0.3

        elif predicted_bps < 40:
            # Decent chance of 1-2 points
            return 1.0

        elif predicted_bps < 50:
            # Good chance of 2-3 points
            return 2.0

        else:
            # Very high BPS, likely 3 points
            return 2.5

    def get_expected_bonus_for_player(
        self,
        player: Player,
        fixture: Fixture,
        predicted_goals: float = 0.0,
        predicted_assists: float = 0.0,
        clean_sheet_prob: float = 0.0,
        minutes_expected: float = 90
    ) -> Tuple[float, float]:
        """
        Get complete bonus prediction for player.

        Returns:
            Tuple of (expected_bps, expected_bonus_points)
        """
        # Predict BPS
        bps = self.predict_bps(
            player,
            fixture,
            minutes_expected=minutes_expected,
            predicted_goals=predicted_goals,
            predicted_assists=predicted_assists,
            clean_sheet_prob=clean_sheet_prob
        )

        # Convert to bonus points
        bonus_points = self.predict_bonus_points(player, fixture, bps)

        return bps, bonus_points

    def get_bonus_magnets(
        self,
        position: Optional[str] = None,
        top_n: int = 20
    ) -> list:
        """
        Identify "bonus magnets" - players who consistently get bonus points.

        These are players with high BPS per 90 due to their playstyle.
        """
        candidates = []

        players = self.data.get_available_players()
        if position:
            players = [p for p in players if p.position == position]

        for player in players:
            if player.minutes < 450:  # Need reasonable sample size
                continue

            # Estimate BPS per 90 based on archetype
            archetype = self._get_player_archetype(player)
            archetype_bps = self.ARCHETYPE_BPS_PER_90[player.position].get(
                archetype,
                self.ARCHETYPE_BPS_PER_90[player.position]['average']
            )

            # Adjust for actual performance
            # Players with high PPG tend to have high BPS
            ppg_multiplier = min(player.points_per_game / 4.0, 1.5)
            estimated_bps_per_90 = archetype_bps * ppg_multiplier

            candidates.append({
                'player': player,
                'estimated_bps_per_90': estimated_bps_per_90,
                'archetype': archetype
            })

        # Sort by BPS per 90
        candidates.sort(key=lambda x: x['estimated_bps_per_90'], reverse=True)

        return candidates[:top_n]
