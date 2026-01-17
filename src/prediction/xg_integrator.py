"""
xG (Expected Goals) integration for FPL predictions.
Uses underlying stats to identify over/under-performing players.

Now enhanced with real xG/xA data from Understat when available!
"""
from typing import Dict, List, Optional, Tuple
from ..data.models import Player, GameweekData
from .understat_client import get_understat_client, PlayerXGStats
import statistics


class XGIntegrator:
    """
    Integrates expected goals (xG) and expected assists (xA) data.

    xG helps identify:
    - Players with good underlying stats but unlucky (underperforming xG)
    - Players overperforming who may regress (outperforming xG)
    - Sustainable point scorers (xG matches actual output)

    Data sources:
    - FPL API: ICT Index (creativity, threat, influence)
    - External: Understat, FBRef, Opta (if available)

    Note: FPL API doesn't provide direct xG, so we use:
    - ICT Threat as proxy for xG (shots, shot quality)
    - ICT Creativity as proxy for xA (key passes, assists)
    - Form vs PPG to identify variance
    """

    # ICT Index thresholds (per 90 minutes)
    # Based on FPL community analysis
    THREAT_EXCELLENT = 80.0    # Elite attacking threat
    THREAT_GOOD = 50.0         # Good attacking threat
    THREAT_AVERAGE = 30.0      # Average threat

    CREATIVITY_EXCELLENT = 80.0
    CREATIVITY_GOOD = 50.0
    CREATIVITY_AVERAGE = 30.0

    # xG adjustment weights
    XG_WEIGHT = 0.15  # 15% weight in final prediction adjustment

    def __init__(self, gameweek_data: GameweekData, api_client, use_understat: bool = True):
        self.data = gameweek_data
        self.api_client = api_client
        self._player_xg_cache = {}
        self.use_understat = use_understat
        self._understat_client = None

        if use_understat:
            try:
                self._understat_client = get_understat_client(league='EPL', season='2025')
            except Exception as e:
                print(f"Warning: Could not initialize Understat client: {e}")
                print("Falling back to ICT proxy method")
                self.use_understat = False

    def _get_player_ict_stats(self, player: Player) -> Optional[Dict]:
        """
        Get ICT (Influence, Creativity, Threat) stats for player.

        ICT Index breakdown:
        - Influence: Overall impact on match
        - Creativity: Chance creation (proxy for xA)
        - Threat: Goal threat (proxy for xG)
        """
        if player.id in self._player_xg_cache:
            return self._player_xg_cache[player.id]

        try:
            # Get detailed player history from API
            history = self.api_client.get_player_details(player.id)

            if history and 'history' in history:
                recent_games = history['history'][-8:]  # Last 8 games

                if not recent_games:
                    return None

                # Calculate average ICT stats (convert strings to floats)
                avg_influence = statistics.mean(float(g.get('influence', 0)) for g in recent_games)
                avg_creativity = statistics.mean(float(g.get('creativity', 0)) for g in recent_games)
                avg_threat = statistics.mean(float(g.get('threat', 0)) for g in recent_games)
                avg_ict_index = statistics.mean(float(g.get('ict_index', 0)) for g in recent_games)

                # Calculate per-90 stats
                total_minutes = sum(g.get('minutes', 0) for g in recent_games)
                if total_minutes > 0:
                    games_played_90 = total_minutes / 90.0

                    influence_per_90 = avg_influence / games_played_90 if games_played_90 > 0 else 0
                    creativity_per_90 = avg_creativity / games_played_90 if games_played_90 > 0 else 0
                    threat_per_90 = avg_threat / games_played_90 if games_played_90 > 0 else 0
                else:
                    influence_per_90 = 0
                    creativity_per_90 = 0
                    threat_per_90 = 0

                result = {
                    'influence': avg_influence,
                    'creativity': avg_creativity,
                    'threat': avg_threat,
                    'ict_index': avg_ict_index,
                    'influence_per_90': influence_per_90,
                    'creativity_per_90': creativity_per_90,
                    'threat_per_90': threat_per_90,
                }

                self._player_xg_cache[player.id] = result
                return result

        except Exception as e:
            print(f"Warning: Could not fetch ICT stats for {player.name}: {e}")

        return None

    def _get_real_xg_stats(self, player: Player) -> Optional[PlayerXGStats]:
        """
        Get real xG/xA stats from Understat (if available).

        Returns:
            PlayerXGStats or None if not available
        """
        if not self.use_understat or not self._understat_client:
            return None

        try:
            # Try to fetch real xG data
            understat_name = self._understat_client.map_fpl_name_to_understat(player.name)
            xg_stats = self._understat_client.get_player_xg_stats(understat_name)
            return xg_stats
        except Exception as e:
            # Silently fail and fall back to ICT
            return None

    def calculate_xg_score(self, player: Player) -> float:
        """
        Calculate xG-based score.
        Uses real Understat xG if available, otherwise ICT threat proxy.

        Returns:
            xG score (0-10+, higher = better underlying stats)
        """
        # Try real xG first
        if self.use_understat:
            real_xg = self._get_real_xg_stats(player)
            if real_xg and real_xg.minutes >= 270:  # At least 3 full games
                # Convert xG per 90 to 0-10 scale
                # Top players have ~0.7 xG per 90 for forwards, ~0.4 for mids
                if player.position == 'FWD':
                    normalized = (real_xg.xG_per_90 + real_xg.xA_per_90) / 0.9 * 10
                elif player.position == 'MID':
                    normalized = (real_xg.xG_per_90 + real_xg.xA_per_90) / 0.6 * 10
                elif player.position == 'DEF':
                    normalized = (real_xg.xG_per_90 + real_xg.xA_per_90) / 0.3 * 10
                else:  # GK
                    normalized = player.form if player.form > 0 else 3.0

                return max(0, min(normalized, 10.0))

        # Fallback to ICT proxy
        ict_stats = self._get_player_ict_stats(player)

        if not ict_stats:
            # Fallback to basic form
            return player.form if player.form > 0 else 2.0

        # Position-specific scoring
        if player.position == 'FWD':
            # Forwards: Heavy weight on threat
            xg_score = (
                ict_stats['threat_per_90'] * 0.70 +
                ict_stats['creativity_per_90'] * 0.20 +
                ict_stats['influence_per_90'] * 0.10
            )
        elif player.position == 'MID':
            # Midfielders: Balanced threat and creativity
            xg_score = (
                ict_stats['threat_per_90'] * 0.40 +
                ict_stats['creativity_per_90'] * 0.40 +
                ict_stats['influence_per_90'] * 0.20
            )
        elif player.position == 'DEF':
            # Defenders: Creativity and influence
            xg_score = (
                ict_stats['threat_per_90'] * 0.20 +
                ict_stats['creativity_per_90'] * 0.30 +
                ict_stats['influence_per_90'] * 0.50
            )
        else:  # GK
            # Goalkeepers: Pure influence
            xg_score = ict_stats['influence_per_90']

        # Normalize to 0-10 scale
        normalized_score = xg_score / 10.0

        return max(0, min(normalized_score, 10.0))

    def calculate_performance_variance(self, player: Player) -> Dict:
        """
        Calculate variance between actual performance and underlying stats.
        Uses real xG data when available for maximum accuracy.

        Identifies:
        - Overperformers (actual > xG) - may regress
        - Underperformers (actual < xG) - may improve
        - Sustainable (actual ≈ xG) - consistent

        Returns:
            Dict with variance analysis
        """
        # Try real xG variance first
        if self.use_understat:
            real_xg = self._get_real_xg_stats(player)
            if real_xg and real_xg.minutes >= 270:
                # Use actual xG variance from Understat
                # Real variance is goals - xG
                variance = real_xg.xG_variance

                if variance > 2.0:
                    classification = 'OVERPERFORMING'
                    risk = f'Scored {real_xg.goals} goals from {real_xg.xG:.1f} xG - may regress'
                elif variance < -2.0:
                    classification = 'UNDERPERFORMING'
                    risk = f'Only {real_xg.goals} goals from {real_xg.xG:.1f} xG - due improvement'
                else:
                    classification = 'SUSTAINABLE'
                    risk = f'{real_xg.goals} goals from {real_xg.xG:.1f} xG - sustainable'

                return {
                    'xg_score': round(real_xg.xG, 2),
                    'xA_score': round(real_xg.xA, 2),
                    'actual_goals': real_xg.goals,
                    'actual_assists': real_xg.assists,
                    'variance': round(variance, 2),
                    'xA_variance': round(real_xg.xA_variance, 2),
                    'classification': classification,
                    'risk_note': risk,
                    'source': 'understat'
                }

        # Fallback to ICT-based variance
        xg_score = self.calculate_xg_score(player)
        actual_form = player.form if player.form > 0 else 0

        # Calculate variance
        # xG score is 0-10, form is typically 0-10
        variance = actual_form - xg_score

        if variance > 2.0:
            classification = 'OVERPERFORMING'
            risk = 'May regress to underlying stats'
        elif variance < -2.0:
            classification = 'UNDERPERFORMING'
            risk = 'May improve based on xG'
        else:
            classification = 'SUSTAINABLE'
            risk = 'Performance matches underlying stats'

        return {
            'xg_score': round(xg_score, 2),
            'actual_form': round(actual_form, 2),
            'variance': round(variance, 2),
            'classification': classification,
            'risk_note': risk,
            'source': 'ict_proxy'
        }

    def adjust_prediction_for_xg(
        self,
        player: Player,
        base_prediction: float
    ) -> Tuple[float, Dict]:
        """
        Adjust expected points prediction based on xG analysis.

        Args:
            player: Player to analyze
            base_prediction: Base expected points from main forecaster

        Returns:
            Tuple of (adjusted_prediction, xg_breakdown_dict)
        """
        variance_analysis = self.calculate_performance_variance(player)
        ict_stats = self._get_player_ict_stats(player)

        if not ict_stats:
            return base_prediction, {'adjustment': 0.0, 'reason': 'No xG data available'}

        # Adjustment based on variance
        variance = variance_analysis['variance']

        if variance > 3.0:
            # Significantly overperforming - reduce prediction
            adjustment_factor = 0.90  # -10%
            reason = 'Overperforming xG - likely regression'
        elif variance > 1.5:
            # Moderately overperforming
            adjustment_factor = 0.95  # -5%
            reason = 'Slight overperformance vs xG'
        elif variance < -3.0:
            # Significantly underperforming - increase prediction
            adjustment_factor = 1.10  # +10%
            reason = 'Underperforming xG - due improvement'
        elif variance < -1.5:
            # Moderately underperforming
            adjustment_factor = 1.05  # +5%
            reason = 'Slight underperformance vs xG'
        else:
            # Sustainable performance
            adjustment_factor = 1.0
            reason = 'Sustainable performance'

        # Apply adjustment with XG_WEIGHT
        # Don't fully apply adjustment, use weight
        weighted_adjustment = 1.0 + (adjustment_factor - 1.0) * self.XG_WEIGHT / 0.15
        adjusted_prediction = base_prediction * weighted_adjustment

        breakdown = {
            'adjustment_factor': round(adjustment_factor, 3),
            'adjusted_prediction': round(adjusted_prediction, 2),
            'reason': reason,
            'xg_score': variance_analysis['xg_score'],
            'variance': variance_analysis['variance'],
        }

        return adjusted_prediction, breakdown

    def get_xg_insights(self, player: Player) -> str:
        """
        Get human-readable xG insights for a player.
        Enhanced with real Understat data when available.

        Returns:
            String with key insights
        """
        variance_analysis = self.calculate_performance_variance(player)
        insights = []

        # Check if we have real xG data
        if variance_analysis.get('source') == 'understat':
            # Real xG insights
            xG = variance_analysis['xg_score']
            xA = variance_analysis['xA_score']

            if player.position == 'FWD' or player.position == 'MID':
                if xG >= 3.0:
                    insights.append(f"🎯 Elite xG: {xG:.1f}")
                elif xG >= 1.5:
                    insights.append(f"⚽ Good xG: {xG:.1f}")

                if xA >= 2.0:
                    insights.append(f"🎨 Elite xA: {xA:.1f}")
                elif xA >= 1.0:
                    insights.append(f"🅰️ Good xA: {xA:.1f}")
        else:
            # ICT-based insights
            ict_stats = self._get_player_ict_stats(player)
            if ict_stats:
                threat = ict_stats['threat_per_90']
                if threat >= self.THREAT_EXCELLENT:
                    insights.append("🎯 Elite goal threat")
                elif threat >= self.THREAT_GOOD:
                    insights.append("⚽ Good goal threat")

                creativity = ict_stats['creativity_per_90']
                if creativity >= self.CREATIVITY_EXCELLENT:
                    insights.append("🎨 Elite chance creation")
                elif creativity >= self.CREATIVITY_GOOD:
                    insights.append("🅰️ Good chance creation")

        # Variance insight
        classification = variance_analysis['classification']
        if classification == 'OVERPERFORMING':
            insights.append("⚠️ Overperforming (may regress)")
        elif classification == 'UNDERPERFORMING':
            insights.append("📈 Underperforming (may improve)")
        else:
            insights.append("✅ Sustainable output")

        return " | ".join(insights) if insights else "Average underlying stats"

    def get_comprehensive_xg_analysis(self, player: Player) -> Dict:
        """
        Get comprehensive xG analysis combining all available data sources.

        Returns:
            Dict with full xG breakdown
        """
        analysis = {
            'player_name': player.name,
            'position': player.position,
            'price': player.price,
            'form': player.form,
            'variance_analysis': self.calculate_performance_variance(player),
            'insights': self.get_xg_insights(player)
        }

        # Add real xG stats if available
        if self.use_understat:
            real_xg = self._get_real_xg_stats(player)
            if real_xg:
                analysis['understat_data'] = {
                    'xG': real_xg.xG,
                    'xA': real_xg.xA,
                    'xG_per_90': real_xg.xG_per_90,
                    'xA_per_90': real_xg.xA_per_90,
                    'goals': real_xg.goals,
                    'assists': real_xg.assists,
                    'shots': real_xg.shots,
                    'key_passes': real_xg.key_passes,
                    'minutes': real_xg.minutes,
                    'games': real_xg.games
                }

        return analysis

    def get_top_xg_underperformers(
        self,
        position: Optional[str] = None,
        top_n: int = 10
    ) -> List[Tuple[Player, Dict]]:
        """
        Find players with best xG but underperforming actual output.
        These are value picks with high upside.

        Args:
            position: Filter by position (None = all)
            top_n: Number of players to return

        Returns:
            List of (player, variance_analysis) tuples
        """
        candidates = []

        players = self.data.get_available_players()
        if position:
            players = [p for p in players if p.position == position]

        for player in players:
            variance_analysis = self.calculate_performance_variance(player)

            # Look for underperformers with good xG
            if (variance_analysis['classification'] == 'UNDERPERFORMING' and
                variance_analysis['xg_score'] >= 4.0):
                candidates.append((player, variance_analysis))

        # Sort by variance (most underperforming first)
        candidates.sort(key=lambda x: x[1]['variance'])

        return candidates[:top_n]

    def get_xg_summary_for_squad(
        self,
        squad_player_ids: List[int]
    ) -> Dict:
        """
        Get xG summary for entire squad.

        Returns:
            Dict with squad-level xG insights
        """
        overperformers = []
        underperformers = []
        sustainable = []

        for player_id in squad_player_ids:
            player = self.data.get_player_by_id(player_id)
            if not player:
                continue

            variance_analysis = self.calculate_performance_variance(player)

            classification = variance_analysis['classification']
            if classification == 'OVERPERFORMING':
                overperformers.append({
                    'name': player.name,
                    'variance': variance_analysis['variance'],
                    'risk': variance_analysis['risk_note']
                })
            elif classification == 'UNDERPERFORMING':
                underperformers.append({
                    'name': player.name,
                    'variance': variance_analysis['variance'],
                    'opportunity': variance_analysis['risk_note']
                })
            else:
                sustainable.append(player.name)

        return {
            'overperformers': overperformers,
            'underperformers': underperformers,
            'sustainable_count': len(sustainable),
            'risk_assessment': (
                'High regression risk' if len(overperformers) >= 5 else
                'Good underlying stats' if len(underperformers) >= 5 else
                'Balanced squad'
            )
        }
