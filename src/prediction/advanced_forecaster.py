"""
Enhanced prediction engine with historical data and advanced features.
"""
from typing import Dict, List, Optional, Tuple
import statistics
from ..data.models import Player, Team, Fixture, GameweekData
from .rotation_predictor import RotationPredictor
from .xg_integrator import XGIntegrator
from .bonus_predictor import BonusPointsPredictor
from .confidence_modeling import ConfidenceModeler, PredictionDistribution


class AdvancedForecaster:
    """
    Advanced player point prediction using historical data and multiple factors.
    """

    # Weight factors for prediction components
    WEIGHTS = {
        # Base prediction weights (MUST sum to 1.0 for accurate predictions)
        'form': 0.60,           # Recent form (last 5 games) - primary predictor
        'ppg': 0.40,            # Season points per game - stability anchor
        # Multiplier weights (applied as adjustments to base, not additive)
        'fixture': 0.25,        # Fixture difficulty adjustment strength
        'minutes': 0.10,        # Minutes reliability (used in formula below)
        'consistency': 0.10,    # Performance consistency (used in formula below)
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

    def __init__(self, gameweek_data: GameweekData, api_client, use_rotation_model: bool = True, use_xg_model: bool = True, use_understat: bool = False, use_bonus_model: bool = True, use_confidence_model: bool = True):
        self.data = gameweek_data
        self.api_client = api_client
        self.team_fixtures = self._organize_fixtures_by_team()
        self.player_history_cache = {}

        # Initialize rotation predictor (Issue #8)
        self.use_rotation_model = use_rotation_model
        if use_rotation_model:
            self.rotation_predictor = RotationPredictor(gameweek_data)
        else:
            self.rotation_predictor = None

        # Initialize xG integrator (Issue #7)
        # NOTE: use_understat disabled by default for speed (10-15 min per GW with Understat)
        # Enable with use_understat=True if you want real xG data (slower but more accurate)
        self.use_xg_model = use_xg_model
        if use_xg_model:
            self.xg_integrator = XGIntegrator(gameweek_data, api_client, use_understat=use_understat)
        else:
            self.xg_integrator = None

        # Initialize bonus points predictor (Phase 2.1)
        self.use_bonus_model = use_bonus_model
        if use_bonus_model:
            self.bonus_predictor = BonusPointsPredictor(gameweek_data, api_client)
        else:
            self.bonus_predictor = None

        # Initialize confidence modeler (Phase 2.2)
        self.use_confidence_model = use_confidence_model
        if use_confidence_model:
            self.confidence_modeler = ConfidenceModeler(gameweek_data)
        else:
            self.confidence_modeler = None

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

        NOTE: Elite players often have high variance (big hauls + blanks).
        This should not penalize them too harshly.
        """
        history = self._get_player_history(player)
        if not history or 'history' not in history:
            return 0.7  # Changed from 0.5 - be more generous

        recent_games = history['history'][-8:]  # Last 8 games
        if len(recent_games) < 3:
            return 0.7

        points = [game['total_points'] for game in recent_games]
        if not points:
            return 0.7

        mean_points = statistics.mean(points)
        if mean_points == 0:
            return 0.5  # Changed from 0.3

        # Calculate coefficient of variation (lower = more consistent)
        stdev = statistics.stdev(points) if len(points) > 1 else 0
        cv = stdev / mean_points if mean_points > 0 else 1.0

        # Convert to 0-1 score (lower CV = higher consistency)
        # SOFTENED: Changed from cv/2 to cv/3 (less harsh penalty)
        # Elite players have high variance but that's actually GOOD (ceiling matters)
        consistency = max(0.3, 1 - (cv / 3))  # Min 0.3 instead of 0.0
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
                return 0.5  # Changed from 0.1 - assume average reliability if no data
            # Estimate games played
            current_gw = self.data.current_gameweek
            games_played = max(current_gw - 1, 1)
            avg_minutes = player.minutes / games_played
            reliability = min(avg_minutes / 90, 1.0)
            # Premium players (high price) should get benefit of doubt
            if player.price >= 10.0 and reliability < 0.7:
                reliability = max(reliability, 0.8)  # Assume they start most games
            return reliability

        recent_games = history['history'][-5:]
        if not recent_games:
            # No recent games but history exists - assume average
            return 0.8 if player.price >= 10.0 else 0.5

        # Calculate average minutes played
        avg_minutes = sum(g['minutes'] for g in recent_games) / len(recent_games)
        reliability = avg_minutes / 90

        # Bonus for consistent starters
        full_games = sum(1 for g in recent_games if g['minutes'] >= 60)
        if full_games >= 4:
            reliability *= 1.1

        # CRITICAL FIX: Premium players with low recent minutes (AFCON, injury)
        # should get benefit of doubt - they'll start when available
        if player.price >= 10.0 and reliability < 0.7:
            reliability = max(reliability, 0.75)  # Assume they'll start most games

        return min(reliability, 1.0)

    def _get_team_form(self, team_id: int, num_games: int = 5) -> float:
        """
        Calculate team form based on recent results.

        Returns a form score (0.0 to 2.0+), where:
        - 1.0 = average form
        - > 1.0 = good form (increases predicted points)
        - < 1.0 = poor form (decreases predicted points)
        """
        # Get all players from this team
        team_players = [p for p in self.data.players if p.team_id == team_id]

        if not team_players:
            return 1.0

        # Calculate average form from team players
        # Form in FPL is weighted points from recent games
        form_values = [p.form for p in team_players if p.form > 0 and p.minutes > 90]

        if not form_values:
            return 1.0

        # Average team form (form is already normalized by FPL)
        avg_form = sum(form_values) / len(form_values)

        # Convert to multiplier: avg form of 3.0 = 1.0x, higher = better
        # Typical form range: 0.5 - 8.0
        form_multiplier = 0.7 + (avg_form / 10.0)  # Maps roughly to 0.75 - 1.5

        return max(0.5, min(1.5, form_multiplier))  # Clamp between 0.5 and 1.5

    def calculate_fixture_difficulty(
        self,
        player: Player,
        num_gameweeks: int = 3
    ) -> float:
        """
        Calculate fixture difficulty multiplier with advanced team strength analysis.

        Enhanced with:
        - Base difficulty (1-5 FPL rating) - 40%
        - Team strength (attack/defense) - 30%
        - Recent form (last 5 games) - 20%
        - Home/away advantage - 10%
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

        # Get player's team form
        team_form = self._get_team_form(player.team_id)

        for fixture in fixtures:
            is_home = fixture.team_h == player.team_id
            opponent_id = fixture.team_a if is_home else fixture.team_h
            opponent = self.data.get_team_by_id(opponent_id)

            if not opponent:
                continue

            # 1. Base difficulty multiplier (40% weight)
            difficulty = fixture.team_h_difficulty if is_home else fixture.team_a_difficulty
            base_mult = self.DIFFICULTY_MULTIPLIERS.get(difficulty, 1.0)

            # 2. Team strength analysis (30% weight)
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
            strength_mult = (
                position_weights['attack'] * attack_factor +
                position_weights['defence'] * defence_factor
            )

            # 3. Recent form analysis (20% weight)
            # Get opponent's form
            opponent_form = self._get_team_form(opponent_id)

            # Good team form vs poor opponent form = higher multiplier
            # Form factor: (my_team_form / opponent_form)
            # If my team is in form 1.3 and opponent is weak 0.8, factor = 1.625
            form_factor = team_form / max(opponent_form, 0.5)
            form_factor = max(0.7, min(form_factor, 1.5))  # Clamp 0.7 - 1.5

            # 4. Home advantage (10% weight in final calculation)
            home_factor = 1.08 if is_home else 1.0

            # Combine all factors with specified weights
            # 40% base + 30% strength + 20% form + 10% home
            fixture_mult = (
                base_mult * 0.40 +
                strength_mult * 0.30 +
                form_factor * 0.20 +
                home_factor * 0.10
            )

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

        # Apply rotation risk adjustment (Issue #8)
        rotation_adjusted = consistency_adjusted
        rotation_risk = 0.0
        if self.use_rotation_model and self.rotation_predictor:
            rotation_risk = self.rotation_predictor.calculate_rotation_risk(
                player,
                self.data.current_gameweek
            )
            # Rotation risk reduces expected points
            rotation_adjusted = consistency_adjusted * (1 - rotation_risk)

        # Apply xG adjustment (Issue #7)
        xg_adjusted = rotation_adjusted
        xg_variance = 0.0
        if self.use_xg_model and self.xg_integrator:
            xg_adjusted, xg_breakdown = self.xg_integrator.adjust_prediction_for_xg(
                player,
                rotation_adjusted
            )
            xg_variance = xg_breakdown.get('variance', 0.0)

        # Add bonus points prediction (Phase 2.1)
        bonus_adjusted = xg_adjusted
        expected_bonus = 0.0
        if self.use_bonus_model and self.bonus_predictor:
            # Get next fixture for this player's team
            fixtures = self.team_fixtures.get(player.team_id, [])
            next_fixtures = sorted(
                [f for f in fixtures if f.event is not None and f.event >= self.data.current_gameweek],
                key=lambda x: x.event
            )[:num_gameweeks]

            if next_fixtures:
                # Estimate goals/assists from xG (simplified)
                predicted_goals = xg_adjusted * 0.15 if player.position in ['FWD', 'MID'] else xg_adjusted * 0.05
                predicted_assists = xg_adjusted * 0.10 if player.position == 'MID' else xg_adjusted * 0.05
                clean_sheet_prob = 0.3 if player.position in ['GK', 'DEF'] else 0.0

                # Predict bonus for first fixture (simplified)
                _, bonus_points = self.bonus_predictor.get_expected_bonus_for_player(
                    player,
                    next_fixtures[0],
                    predicted_goals=predicted_goals,
                    predicted_assists=predicted_assists,
                    clean_sheet_prob=clean_sheet_prob,
                    minutes_expected=90 * minutes_reliability
                )

                expected_bonus = bonus_points * num_gameweeks
                bonus_adjusted = xg_adjusted + expected_bonus

        # Scale to number of gameweeks
        total_prediction = bonus_adjusted * num_gameweeks

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
                'rotation_risk': round(rotation_risk, 3),
                'xg_variance': round(xg_variance, 2),
                'expected_bonus': round(expected_bonus, 2),
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

    def predict_with_confidence(
        self,
        player: Player,
        num_gameweeks: int = 3,
        risk_tolerance: str = 'balanced'
    ) -> Tuple[float, PredictionDistribution]:
        """
        Predict points with confidence intervals and uncertainty modeling.

        Args:
            player: Player to predict for
            num_gameweeks: Number of gameweeks to predict
            risk_tolerance: 'conservative', 'balanced', or 'aggressive'

        Returns:
            (risk_adjusted_value, distribution) tuple
        """
        if not self.use_confidence_model or not self.confidence_modeler:
            # Fallback to regular prediction
            mean_pred = self.predict_points(player, num_gameweeks)
            return mean_pred, None

        # Get detailed prediction for components
        detailed = self.predict_points(player, num_gameweeks, detailed=True)
        mean_prediction = detailed['total']

        # Get player history for variance calculation
        history = self._get_player_history(player)

        # Get rotation risk
        rotation_risk = detailed.get('rotation_risk', 0.0)

        # Get fixture difficulty
        fixture_mult = detailed.get('fixture_mult', 1.0)

        # Generate prediction distribution
        distribution = self.confidence_modeler.predict_with_confidence(
            player,
            mean_prediction=mean_prediction,
            gameweeks_ahead=num_gameweeks,
            rotation_risk=rotation_risk,
            fixture_difficulty=fixture_mult,
            history=history
        )

        # Get risk-adjusted value
        risk_adjusted = distribution.get_risk_adjusted_value(risk_tolerance)

        return risk_adjusted, distribution

    def get_predictions_with_confidence(
        self,
        num_gameweeks: int = 3,
        risk_tolerance: str = 'balanced'
    ) -> Dict[int, Tuple[float, PredictionDistribution]]:
        """
        Get predictions with confidence for all available players.

        Args:
            num_gameweeks: Number of gameweeks to predict
            risk_tolerance: Risk tolerance setting

        Returns:
            Dict mapping player_id to (risk_adjusted_value, distribution)
        """
        predictions = {}
        available_players = self.data.get_available_players()

        print(f"  Generating predictions with confidence intervals for {len(available_players)} players...")

        for i, player in enumerate(available_players):
            predictions[player.id] = self.predict_with_confidence(
                player,
                num_gameweeks,
                risk_tolerance
            )

            # Progress indicator
            if (i + 1) % 100 == 0:
                print(f"    Processed {i + 1}/{len(available_players)} players...")

        return predictions
