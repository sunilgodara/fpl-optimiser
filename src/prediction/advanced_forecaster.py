"""
Enhanced prediction engine with historical data and advanced features.
"""
from typing import Dict, List, Optional, Tuple
import statistics
from ..data.models import Player, Team, Fixture, GameweekData


class AdvancedForecaster:
    """
    Advanced player point prediction using historical data and multiple factors.
    """

    # Weight factors for prediction components
    WEIGHTS = {
        'form': 0.35,           # Recent form (last 5 games)
        'ppg': 0.20,            # Season points per game
        'fixture': 0.25,        # Fixture difficulty
        'minutes': 0.10,        # Minutes played reliability
        'consistency': 0.10,    # Performance consistency
    }

    # Fixture difficulty multipliers (refined)
    DIFFICULTY_MULTIPLIERS = {
        1: 1.35,
        2: 1.18,
        3: 1.0,
        4: 0.82,
        5: 0.65,
    }

    # Position-specific weights for fixture analysis
    POSITION_FIXTURE_WEIGHTS = {
        'GK': {'defence': 0.85, 'attack': 0.15},
        'DEF': {'defence': 0.70, 'attack': 0.30},
        'MID': {'defence': 0.25, 'attack': 0.75},
        'FWD': {'defence': 0.05, 'attack': 0.95},
    }

    def __init__(self, gameweek_data: GameweekData, api_client):
        self.data = gameweek_data
        self.api_client = api_client
        self.team_fixtures = self._organize_fixtures_by_team()
        self.player_history_cache = {}

    def _organize_fixtures_by_team(self) -> Dict[int, List[Fixture]]:
        """Organize fixtures by team ID."""
        team_fixtures = {}
        for fixture in self.data.fixtures:
            if fixture.team_h not in team_fixtures:
                team_fixtures[fixture.team_h] = []
            team_fixtures[fixture.team_h].append(fixture)

            if fixture.team_a not in team_fixtures:
                team_fixtures[fixture.team_a] = []
            team_fixtures[fixture.team_a].append(fixture)

        return team_fixtures

    def _get_player_history(self, player: Player) -> Optional[Dict]:
        """Fetch historical data for a player (cached)."""
        if player.id in self.player_history_cache:
            return self.player_history_cache[player.id]

        try:
            history = self.api_client.get_player_details(player.id)
            self.player_history_cache[player.id] = history
            return history
        except Exception as e:
            print(f"Warning: Could not fetch history for {player.name}: {e}")
            return None

    def calculate_form_score(self, player: Player) -> float:
        """
        Calculate form score based on recent performances.
        Uses last 5 gameweeks with exponential weighting (more recent = higher weight).
        """
        history = self._get_player_history(player)
        if not history or 'history' not in history:
            return float(player.form) if player.form > 0 else 2.0

        recent_games = history['history'][-5:]  # Last 5 games
        if not recent_games:
            return 2.0

        # Exponentially weighted average (more recent = higher weight)
        weights = [0.1, 0.15, 0.20, 0.25, 0.30]  # Sum = 1.0
        weighted_points = sum(
            game['total_points'] * weights[i]
            for i, game in enumerate(recent_games[-len(weights):])
        )

        # Boost if player is on upward trend
        if len(recent_games) >= 3:
            recent_avg = sum(g['total_points'] for g in recent_games[-2:]) / 2
            older_avg = sum(g['total_points'] for g in recent_games[-5:-2]) / 3 if len(recent_games) >= 5 else recent_avg
            if recent_avg > older_avg * 1.2:
                weighted_points *= 1.1  # 10% boost for trending up

        return max(weighted_points, 0.5)

    def calculate_consistency_score(self, player: Player) -> float:
        """
        Calculate consistency score (0-1).
        Penalizes players who have high variance in points.
        """
        history = self._get_player_history(player)
        if not history or 'history' not in history:
            return 0.5

        recent_games = history['history'][-8:]  # Last 8 games
        if len(recent_games) < 3:
            return 0.5

        points = [game['total_points'] for game in recent_games]
        if not points:
            return 0.5

        mean_points = statistics.mean(points)
        if mean_points == 0:
            return 0.3

        # Calculate coefficient of variation (lower = more consistent)
        stdev = statistics.stdev(points) if len(points) > 1 else 0
        cv = stdev / mean_points if mean_points > 0 else 1.0

        # Convert to 0-1 score (lower CV = higher consistency)
        consistency = max(0, 1 - (cv / 2))  # Normalize assuming CV rarely > 2
        return min(consistency, 1.0)

    def calculate_minutes_reliability(self, player: Player) -> float:
        """
        Calculate minutes reliability (0-1).
        Higher score for players who consistently play full 90 minutes.
        """
        history = self._get_player_history(player)
        if not history or 'history' not in history:
            # Fallback to season minutes
            if player.minutes == 0:
                return 0.1
            # Estimate games played
            current_gw = self.data.current_gameweek
            avg_minutes = player.minutes / max(current_gw - 1, 1)
            return min(avg_minutes / 90, 1.0)

        recent_games = history['history'][-5:]
        if not recent_games:
            return 0.1

        # Calculate average minutes played
        avg_minutes = sum(g['minutes'] for g in recent_games) / len(recent_games)
        reliability = avg_minutes / 90

        # Bonus for consistent starters
        full_games = sum(1 for g in recent_games if g['minutes'] >= 60)
        if full_games >= 4:
            reliability *= 1.1

        return min(reliability, 1.0)

    def calculate_fixture_difficulty(
        self,
        player: Player,
        num_gameweeks: int = 3
    ) -> float:
        """
        Calculate fixture difficulty multiplier with advanced team strength analysis.
        """
        fixtures = self.team_fixtures.get(player.team_id, [])
        if not fixtures:
            return 1.0

        # Get next N fixtures
        fixtures = sorted(
            [f for f in fixtures if f.event is not None and f.event >= self.data.current_gameweek],
            key=lambda x: x.event
        )[:num_gameweeks]

        if not fixtures:
            return 1.0

        multipliers = []
        position_weights = self.POSITION_FIXTURE_WEIGHTS[player.position]

        for fixture in fixtures:
            is_home = fixture.team_h == player.team_id
            opponent_id = fixture.team_a if is_home else fixture.team_h
            opponent = self.data.get_team_by_id(opponent_id)

            if not opponent:
                continue

            # Basic difficulty multiplier
            difficulty = fixture.team_h_difficulty if is_home else fixture.team_a_difficulty
            base_mult = self.DIFFICULTY_MULTIPLIERS.get(difficulty, 1.0)

            # Advanced: Consider opponent's specific strengths
            if is_home:
                opp_attack = opponent.strength_attack_away
                opp_defence = opponent.strength_defence_away
            else:
                opp_attack = opponent.strength_attack_home
                opp_defence = opponent.strength_defence_home

            # Normalize strengths (typical range: 1000-1400)
            # Lower opponent defence = easier for attackers
            # Lower opponent attack = easier for defenders
            attack_factor = 1.0 + (1250 - opp_defence) / 500
            defence_factor = 1.0 + (1250 - opp_attack) / 500

            # Combine based on position
            position_mult = (
                position_weights['attack'] * attack_factor +
                position_weights['defence'] * defence_factor
            )

            # Home advantage
            if is_home:
                position_mult *= 1.08

            # Blend basic and advanced multipliers
            fixture_mult = (base_mult * 0.6) + (position_mult * 0.4)
            multipliers.append(fixture_mult)

        return sum(multipliers) / len(multipliers) if multipliers else 1.0

    def predict_points(
        self,
        player: Player,
        num_gameweeks: int = 3,
        detailed: bool = False
    ) -> float:
        """
        Predict expected points with advanced multi-factor analysis.

        Args:
            player: Player to predict for
            num_gameweeks: Number of gameweeks to predict
            detailed: If True, return breakdown dict

        Returns:
            Expected points (or dict if detailed=True)
        """
        if not player.is_available():
            return 0.0 if not detailed else {'total': 0.0, 'reason': 'unavailable'}

        # Calculate component scores
        form_score = self.calculate_form_score(player)
        ppg_score = player.points_per_game
        consistency = self.calculate_consistency_score(player)
        minutes_reliability = self.calculate_minutes_reliability(player)
        fixture_mult = self.calculate_fixture_difficulty(player, num_gameweeks)

        # Base prediction from form and PPG
        base_prediction = (
            self.WEIGHTS['form'] * form_score +
            self.WEIGHTS['ppg'] * ppg_score
        )

        # Apply fixture difficulty
        fixture_adjusted = base_prediction * (
            1 + (fixture_mult - 1) * self.WEIGHTS['fixture'] / self.WEIGHTS['form']
        )

        # Apply minutes reliability (reduce if not playing regularly)
        minutes_adjusted = fixture_adjusted * (
            0.5 + 0.5 * minutes_reliability  # Min 50% if rarely plays
        )

        # Apply consistency (reduce if inconsistent)
        consistency_adjusted = minutes_adjusted * (
            0.85 + 0.15 * consistency  # Min 85% for inconsistent players
        )

        # Scale to number of gameweeks
        total_prediction = consistency_adjusted * num_gameweeks

        # Ensure minimum for players who play
        if minutes_reliability > 0.5:
            total_prediction = max(total_prediction, 1.0 * num_gameweeks)

        if detailed:
            return {
                'total': round(total_prediction, 2),
                'base_ppg': round(base_prediction, 2),
                'form_score': round(form_score, 2),
                'fixture_mult': round(fixture_mult, 2),
                'minutes_reliability': round(minutes_reliability, 2),
                'consistency': round(consistency, 2),
            }

        return round(total_prediction, 2)

    def get_predictions_for_all_players(
        self,
        num_gameweeks: int = 3
    ) -> Dict[int, float]:
        """Get predictions for all available players."""
        predictions = {}
        available_players = self.data.get_available_players()

        print(f"  Generating predictions for {len(available_players)} available players...")

        for i, player in enumerate(available_players):
            predictions[player.id] = self.predict_points(player, num_gameweeks)

            # Progress indicator for large datasets
            if (i + 1) % 100 == 0:
                print(f"    Processed {i + 1}/{len(available_players)} players...")

        return predictions

    def get_top_predicted_players(
        self,
        num_gameweeks: int = 3,
        top_n: int = 20
    ) -> List[Tuple[Player, float, Dict]]:
        """
        Get top N predicted players with detailed breakdowns.

        Returns:
            List of (player, expected_points, breakdown_dict)
        """
        results = []
        for player in self.data.get_available_players():
            detailed = self.predict_points(player, num_gameweeks, detailed=True)
            results.append((player, detailed['total'], detailed))

        results.sort(key=lambda x: x[1], reverse=True)
        return results[:top_n]
