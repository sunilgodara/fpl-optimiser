"""
Understat API client for fetching real xG/xA data.

This module provides access to actual expected goals (xG) and expected assists (xA)
data from Understat, which is significantly more accurate than using ICT proxies.
"""
from typing import Dict, List, Optional, Tuple
import time
from dataclasses import dataclass


@dataclass
class PlayerXGStats:
    """Real xG/xA statistics from Understat."""
    player_name: str
    team: str
    games: int
    minutes: int
    goals: int
    xG: float  # Expected goals
    assists: int
    xA: float  # Expected assists
    shots: int
    key_passes: int
    xG_per_90: float
    xA_per_90: float
    xG_variance: float  # goals - xG (positive = overperforming)
    xA_variance: float  # assists - xA (positive = overperforming)


class UnderstatClient:
    """
    Client for fetching xG data from Understat.

    Understat provides:
    - xG (Expected Goals): Shot quality based on location, body part, assist type
    - xA (Expected Assists): Quality of chances created
    - Per-game and per-90 statistics
    - Home/away splits
    """

    def __init__(self, league: str = 'EPL', season: str = '2025'):
        """
        Initialize Understat client.

        Args:
            league: League code ('EPL', 'La_Liga', 'Bundesliga', etc.)
            season: Season year (e.g., '2025' for 2025/26 season)
        """
        self.league = league
        self.season = season
        self._cache: Dict[str, PlayerXGStats] = {}
        self._last_request_time = 0
        self._rate_limit_delay = 1.0  # 1 second between requests

    def _rate_limit(self):
        """Enforce rate limiting to avoid overwhelming Understat."""
        elapsed = time.time() - self._last_request_time
        if elapsed < self._rate_limit_delay:
            time.sleep(self._rate_limit_delay - elapsed)
        self._last_request_time = time.time()

    def get_player_xg_stats(self, player_name: str) -> Optional[PlayerXGStats]:
        """
        Fetch real xG/xA stats for a player from Understat.

        Args:
            player_name: Player's full name (e.g., "Mohamed Salah")

        Returns:
            PlayerXGStats with xG/xA data, or None if not found
        """
        # Check cache first
        if player_name in self._cache:
            return self._cache[player_name]

        try:
            # Import here to avoid dependency issues if not installed
            from understatapi import UnderstatClient as UClient

            self._rate_limit()

            # Fetch league data
            client = UClient()
            league_data = client.league(league=self.league).get_player_data(season=self.season)

            # Find player in league data
            for player_data in league_data:
                if player_data['player_name'].lower() == player_name.lower():
                    stats = self._parse_player_data(player_data)
                    self._cache[player_name] = stats
                    return stats

            # Player not found
            return None

        except ImportError:
            print("Warning: understatapi not installed. Run: pip install understatapi")
            return None
        except Exception as e:
            print(f"Warning: Could not fetch Understat data for {player_name}: {e}")
            return None

    def _parse_player_data(self, data: Dict) -> PlayerXGStats:
        """Parse Understat API response into PlayerXGStats."""
        games = int(data.get('games', 0))
        minutes = int(data.get('time', 0))

        # Extract stats (convert strings to floats)
        goals = int(data.get('goals', 0))
        xG = float(data.get('xG', 0))
        assists = int(data.get('assists', 0))
        xA = float(data.get('xA', 0))
        shots = int(data.get('shots', 0))
        key_passes = int(data.get('key_passes', 0))

        # Calculate per-90 stats
        if minutes > 0:
            minutes_per_90 = minutes / 90.0
            xG_per_90 = xG / minutes_per_90
            xA_per_90 = xA / minutes_per_90
        else:
            xG_per_90 = 0
            xA_per_90 = 0

        # Calculate variance (over/underperformance)
        xG_variance = goals - xG
        xA_variance = assists - xA

        return PlayerXGStats(
            player_name=data.get('player_name', ''),
            team=data.get('team_title', ''),
            games=games,
            minutes=minutes,
            goals=goals,
            xG=round(xG, 2),
            assists=assists,
            xA=round(xA, 2),
            shots=shots,
            key_passes=key_passes,
            xG_per_90=round(xG_per_90, 2),
            xA_per_90=round(xA_per_90, 2),
            xG_variance=round(xG_variance, 2),
            xA_variance=round(xA_variance, 2)
        )

    def get_league_top_xg_players(self, top_n: int = 20) -> List[PlayerXGStats]:
        """
        Get top players by xG in the league.

        Args:
            top_n: Number of players to return

        Returns:
            List of PlayerXGStats sorted by xG
        """
        try:
            from understatapi import UnderstatClient as UClient

            self._rate_limit()

            client = UClient()
            league_data = client.league(league=self.league).get_player_data(season=self.season)

            players = [self._parse_player_data(p) for p in league_data]
            players.sort(key=lambda x: x.xG, reverse=True)

            return players[:top_n]

        except Exception as e:
            print(f"Warning: Could not fetch top xG players: {e}")
            return []

    def find_xg_value_picks(
        self,
        min_minutes: int = 450,
        xg_variance_threshold: float = -2.0
    ) -> List[PlayerXGStats]:
        """
        Find players underperforming their xG (value picks).

        These players have good underlying stats but haven't converted chances yet.
        They're likely to improve and represent good value.

        Args:
            min_minutes: Minimum minutes played to qualify
            xg_variance_threshold: Maximum variance (negative = underperforming)

        Returns:
            List of underperforming players sorted by xG variance
        """
        try:
            from understatapi import UnderstatClient as UClient

            self._rate_limit()

            client = UClient()
            league_data = client.league(league=self.league).get_player_data(season=self.season)

            # Filter underperformers
            value_picks = []
            for player_data in league_data:
                stats = self._parse_player_data(player_data)

                if (stats.minutes >= min_minutes and
                    stats.xG_variance <= xg_variance_threshold and
                    stats.xG >= 1.0):  # At least some goal threat
                    value_picks.append(stats)

            # Sort by underperformance (most underperforming first)
            value_picks.sort(key=lambda x: x.xG_variance)

            return value_picks[:15]  # Top 15 value picks

        except Exception as e:
            print(f"Warning: Could not find xG value picks: {e}")
            return []

    def get_team_xg_stats(self, team_name: str) -> Dict:
        """
        Get aggregate xG stats for a team.

        Args:
            team_name: Team name (e.g., "Liverpool")

        Returns:
            Dict with team xG statistics
        """
        try:
            from understatapi import UnderstatClient as UClient

            self._rate_limit()

            client = UClient()
            team_data = client.team(team=team_name).get_season_data(season=self.season)

            # Parse team stats
            total_xG = sum(float(match.get('xG', 0)) for match in team_data)
            total_xGA = sum(float(match.get('xGA', 0)) for match in team_data)  # xG against
            total_goals = sum(int(match.get('scored', 0)) for match in team_data)
            total_conceded = sum(int(match.get('missed', 0)) for match in team_data)

            return {
                'team': team_name,
                'matches': len(team_data),
                'xG': round(total_xG, 2),
                'xGA': round(total_xGA, 2),
                'goals_scored': total_goals,
                'goals_conceded': total_conceded,
                'xG_per_game': round(total_xG / len(team_data), 2) if team_data else 0,
                'xGA_per_game': round(total_xGA / len(team_data), 2) if team_data else 0,
                'attack_variance': round(total_goals - total_xG, 2),
                'defense_variance': round(total_conceded - total_xGA, 2)
            }

        except Exception as e:
            print(f"Warning: Could not fetch team xG stats for {team_name}: {e}")
            return {}

    def map_fpl_name_to_understat(self, fpl_name: str) -> str:
        """
        Map FPL player name to Understat name format.

        FPL and Understat sometimes use different name formats.
        This method attempts common transformations.

        Args:
            fpl_name: Player name from FPL API

        Returns:
            Understat-compatible name
        """
        # Common transformations
        name_mappings = {
            'Mohamed Salah': 'Mohamed Salah',
            'Son Heung-min': 'Heung-Min Son',
            # Add more mappings as needed
        }

        return name_mappings.get(fpl_name, fpl_name)


# Singleton instance for caching across requests
_understat_client_instance = None


def get_understat_client(league: str = 'EPL', season: str = '2025') -> UnderstatClient:
    """Get singleton Understat client instance."""
    global _understat_client_instance
    if _understat_client_instance is None:
        _understat_client_instance = UnderstatClient(league=league, season=season)
    return _understat_client_instance
