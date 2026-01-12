"""
Rotation risk modeling for predicting player minutes.
Especially important for teams with fixture congestion (Pep Roulette!).
"""
from typing import Dict, List
from ..data.models import Player, GameweekData, Fixture


class RotationPredictor:
    """
    Predicts rotation risk based on fixture congestion and manager tendencies.

    Key factors:
    - Fixture density (games in next 7 days)
    - European competition (CL/EL mid-week)
    - Manager rotation tendency (Pep > Arteta > others)
    - Recent minutes played
    - Team position/squad depth
    """

    # Manager rotation tendency (higher = more rotation)
    # Based on historical data and community knowledge
    MANAGER_ROTATION_RISK = {
        'MCI': 0.35,  # Pep Guardiola - highest rotation
        'ARS': 0.25,  # Mikel Arteta - moderate-high rotation
        'LIV': 0.20,  # Arne Slot - moderate rotation
        'CHE': 0.25,  # Enzo Maresca - moderate-high rotation
        'TOT': 0.20,  # Ange Postecoglou - moderate rotation
        'MUN': 0.22,  # Ruben Amorim - moderate rotation
        'NEW': 0.15,  # Eddie Howe - lower rotation
        'AVL': 0.18,  # Unai Emery - moderate-low rotation
        # Default for other teams
        'default': 0.15
    }

    # European competition multiplier
    EUROPEAN_COMPETITION_MULTIPLIER = 1.4  # 40% more rotation risk

    def __init__(self, gameweek_data: GameweekData):
        self.data = gameweek_data
        # Cache fixture density calculations
        self._fixture_density_cache = {}

    def calculate_fixture_density(self, team_id: int, current_gw: int) -> int:
        """
        Calculate number of fixtures in the next 7 days for a team.

        Returns:
            Number of fixtures in next 7 days
        """
        if team_id in self._fixture_density_cache:
            return self._fixture_density_cache[team_id]

        # Get team's upcoming fixtures
        team_fixtures = [
            f for f in self.data.fixtures
            if (f.team_h == team_id or f.team_a == team_id) and
            f.event is not None and
            f.event >= current_gw and
            f.event <= current_gw + 1  # Next 2 gameweeks ≈ 7-14 days
        ]

        fixture_count = len(team_fixtures)
        self._fixture_density_cache[team_id] = fixture_count

        return fixture_count

    def get_manager_rotation_tendency(self, team_id: int) -> float:
        """
        Get rotation tendency for team's manager.

        Returns:
            Rotation risk factor (0.0 = no rotation, 0.35 = high rotation)
        """
        team = self.data.get_team_by_id(team_id)
        if not team:
            return self.MANAGER_ROTATION_RISK['default']

        # Use team short name to look up manager tendency
        return self.MANAGER_ROTATION_RISK.get(
            team.short_name,
            self.MANAGER_ROTATION_RISK['default']
        )

    def is_european_competition_week(self, current_gw: int) -> bool:
        """
        Check if there's European competition this week.

        In real implementation, this would check actual CL/EL fixtures.
        For now, we assume European games every other week during season.

        Returns:
            True if European competition is active
        """
        # Simplified: Assume CL/EL weeks are GW 2, 4, 6, 8, 10, 12, 14...
        # Real implementation would check actual UEFA fixture calendar
        return current_gw % 2 == 0 and current_gw <= 32

    def calculate_rotation_risk(
        self,
        player: Player,
        current_gw: int
    ) -> float:
        """
        Calculate rotation risk for a player.

        Returns:
            Rotation risk score (0.0 = no risk, 1.0 = very high risk)
        """
        # Base rotation risk from manager
        base_risk = self.get_manager_rotation_tendency(player.team_id)

        # Adjust for fixture density
        fixture_density = self.calculate_fixture_density(player.team_id, current_gw)
        if fixture_density >= 3:
            # 3+ games in 2 weeks = very high congestion
            density_multiplier = 1.5
        elif fixture_density == 2:
            # 2 games = moderate congestion
            density_multiplier = 1.2
        else:
            # 1 game = normal, no extra rotation
            density_multiplier = 1.0

        # Adjust for European competition
        european_multiplier = 1.0
        if self.is_european_competition_week(current_gw):
            # Check if team is in Europe (simplified: top 6 teams)
            team = self.data.get_team_by_id(player.team_id)
            if team and team.short_name in ['MCI', 'ARS', 'LIV', 'CHE', 'TOT', 'MUN', 'AVL', 'NEW']:
                european_multiplier = self.EUROPEAN_COMPETITION_MULTIPLIER

        # Adjust for recent minutes (if player played 90min recently, higher rotation risk)
        minutes_multiplier = 1.0
        if player.minutes > 0:
            # If averaging close to 90 minutes, higher rotation risk
            avg_minutes = player.minutes / max(player.games_played, 1) if player.games_played > 0 else 0
            if avg_minutes > 80:
                minutes_multiplier = 1.15  # 15% more rotation risk for high-minute players

        # Combined rotation risk
        total_risk = base_risk * density_multiplier * european_multiplier * minutes_multiplier

        # Clamp between 0 and 0.8 (max 80% rotation risk)
        return min(total_risk, 0.8)

    def adjust_expected_points_for_rotation(
        self,
        player: Player,
        expected_points: float,
        current_gw: int
    ) -> float:
        """
        Adjust expected points based on rotation risk.

        Formula: adjusted_EP = EP × (1 - rotation_risk)

        Args:
            player: Player to adjust
            expected_points: Base expected points
            current_gw: Current gameweek

        Returns:
            Rotation-adjusted expected points
        """
        rotation_risk = self.calculate_rotation_risk(player, current_gw)

        # Rotation risk reduces expected points
        # E.g., 30% rotation risk = 70% of expected points
        adjusted_ep = expected_points * (1 - rotation_risk)

        return adjusted_ep

    def get_rotation_explanation(
        self,
        player: Player,
        current_gw: int
    ) -> str:
        """
        Get human-readable explanation of rotation risk.

        Returns:
            Explanation string (e.g., "High rotation risk (Pep + fixture congestion)")
        """
        rotation_risk = self.calculate_rotation_risk(player, current_gw)

        if rotation_risk < 0.15:
            return "Low rotation risk"
        elif rotation_risk < 0.25:
            return "Moderate rotation risk"
        elif rotation_risk < 0.35:
            return "High rotation risk (fixture congestion)"
        else:
            team = self.data.get_team_by_id(player.team_id)
            manager_note = ""
            if team and team.short_name == 'MCI':
                manager_note = " (Pep Roulette!)"
            elif team and team.short_name in ['ARS', 'CHE']:
                manager_note = " (high rotation manager)"

            return f"Very high rotation risk{manager_note}"
