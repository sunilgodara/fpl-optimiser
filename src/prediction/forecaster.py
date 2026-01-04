"""
Player point prediction engine based on form and fixture difficulty.
"""
from typing import Dict, List
from ..data.models import Player, Team, Fixture, GameweekData


class PointForecaster:
    """Predicts player points based on form and fixture difficulty."""

    # Fixture difficulty adjustment factors
    # These adjust expected points based on opponent strength (1=easiest, 5=hardest)
    DIFFICULTY_MULTIPLIERS = {
        1: 1.3,   # Very easy fixture - boost points
        2: 1.15,  # Easy fixture
        3: 1.0,   # Average fixture
        4: 0.85,  # Hard fixture
        5: 0.7,   # Very hard fixture
    }

    # Position-specific adjustments for defensive vs attacking fixtures
    POSITION_WEIGHTS = {
        'GK': {'defence': 0.8, 'attack': 0.2},
        'DEF': {'defence': 0.7, 'attack': 0.3},
        'MID': {'defence': 0.3, 'attack': 0.7},
        'FWD': {'defence': 0.1, 'attack': 0.9},
    }

    def __init__(self, gameweek_data: GameweekData):
        self.data = gameweek_data
        self.team_fixtures = self._organize_fixtures_by_team()

    def _organize_fixtures_by_team(self) -> Dict[int, List[Fixture]]:
        """Organize fixtures by team ID for quick lookup."""
        team_fixtures = {}
        for fixture in self.data.fixtures:
            # Home team
            if fixture.team_h not in team_fixtures:
                team_fixtures[fixture.team_h] = []
            team_fixtures[fixture.team_h].append(fixture)

            # Away team
            if fixture.team_a not in team_fixtures:
                team_fixtures[fixture.team_a] = []
            team_fixtures[fixture.team_a].append(fixture)

        return team_fixtures

    def get_base_expected_points(self, player: Player) -> float:
        """
        Calculate base expected points from player's recent form.

        Uses FPL's form metric (average points over last few games)
        and points per game, weighted towards recent form.
        """
        if player.minutes < 90:  # Player hasn't played much
            return 0.5

        # Weight recent form more heavily than overall PPG
        form_weight = 0.7
        ppg_weight = 0.3

        form = player.form if player.form > 0 else player.points_per_game
        base_points = (form_weight * form) + (ppg_weight * player.points_per_game)

        return max(base_points, 0.5)  # Minimum 0.5 points

    def get_fixture_difficulty_for_team(
        self,
        team_id: int,
        num_gameweeks: int = 3
    ) -> float:
        """
        Get average fixture difficulty for a team over next N gameweeks.

        Returns average difficulty rating (1-5).
        """
        fixtures = self.team_fixtures.get(team_id, [])
        if not fixtures:
            return 3.0  # Neutral if no fixtures found

        # Sort by gameweek and take next N
        fixtures = sorted(
            [f for f in fixtures if f.event is not None],
            key=lambda x: x.event
        )[:num_gameweeks]

        if not fixtures:
            return 3.0

        difficulties = []
        for fixture in fixtures:
            if fixture.team_h == team_id:
                difficulties.append(fixture.team_h_difficulty)
            else:
                difficulties.append(fixture.team_a_difficulty)

        return sum(difficulties) / len(difficulties) if difficulties else 3.0

    def get_fixture_multiplier(
        self,
        player: Player,
        num_gameweeks: int = 3
    ) -> float:
        """
        Calculate fixture difficulty multiplier for a player.

        Considers:
        - Opponent strength (difficulty rating)
        - Home/away split
        - Player position (defenders benefit from weak attacks, forwards from weak defences)
        """
        fixtures = self.team_fixtures.get(player.team_id, [])
        if not fixtures:
            return 1.0

        # Get next N fixtures
        fixtures = sorted(
            [f for f in fixtures if f.event is not None],
            key=lambda x: x.event
        )[:num_gameweeks]

        if not fixtures:
            return 1.0

        multipliers = []
        for fixture in fixtures:
            # Determine if home or away
            is_home = fixture.team_h == player.team_id
            difficulty = fixture.team_h_difficulty if is_home else fixture.team_a_difficulty

            # Get opponent team
            opponent_id = fixture.team_a if is_home else fixture.team_h
            opponent = self.data.get_team_by_id(opponent_id)

            if opponent:
                # Calculate position-specific multiplier
                # Defensive players benefit from weak attacks
                # Attacking players benefit from weak defences
                weights = self.POSITION_WEIGHTS[player.position]

                if is_home:
                    opp_attack_strength = opponent.strength_attack_away
                    opp_defence_strength = opponent.strength_defence_away
                else:
                    opp_attack_strength = opponent.strength_attack_home
                    opp_defence_strength = opponent.strength_defence_home

                # Convert opponent strengths to multipliers (lower = easier for player)
                # Strong attack = harder for defenders, strong defence = harder for attackers
                attack_mult = 1.0 + (3.5 - opp_attack_strength / 300)  # Normalize ~1000-1400
                defence_mult = 1.0 + (3.5 - opp_defence_strength / 300)

                position_mult = (
                    weights['defence'] * attack_mult +
                    weights['attack'] * defence_mult
                ) / 2

                # Combine with basic difficulty multiplier
                base_mult = self.DIFFICULTY_MULTIPLIERS.get(difficulty, 1.0)
                fixture_mult = (base_mult + position_mult) / 2
                multipliers.append(fixture_mult)
            else:
                # Fallback to basic difficulty
                multipliers.append(self.DIFFICULTY_MULTIPLIERS.get(difficulty, 1.0))

        return sum(multipliers) / len(multipliers) if multipliers else 1.0

    def predict_points(
        self,
        player: Player,
        num_gameweeks: int = 3
    ) -> float:
        """
        Predict expected points for a player over next N gameweeks.

        Args:
            player: Player to predict points for
            num_gameweeks: Number of gameweeks to predict for

        Returns:
            Expected total points over the gameweeks
        """
        if not player.is_available():
            return 0.0

        # Get base expected points per gameweek
        base_ppg = self.get_base_expected_points(player)

        # Apply fixture difficulty multiplier
        fixture_mult = self.get_fixture_multiplier(player, num_gameweeks)

        # Total expected points
        expected_points = base_ppg * fixture_mult * num_gameweeks

        return round(expected_points, 2)

    def get_predictions_for_all_players(
        self,
        num_gameweeks: int = 3
    ) -> Dict[int, float]:
        """
        Get predicted points for all players.

        Returns:
            Dict mapping player_id -> expected_points
        """
        predictions = {}
        for player in self.data.players:
            predictions[player.id] = self.predict_points(player, num_gameweeks)

        return predictions
