"""
Understat API client for fetching real xG/xA data.

This module provides access to actual expected goals (xG) and expected assists (xA)
data from Understat, which is significantly more accurate than using ICT proxies.

PERFORMANCE: Fetches entire league data in ONE bulk call and caches locally.
"""
from typing import Dict, List, Optional, Tuple
import time
import json
from pathlib import Path
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta


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

    OPTIMIZED: Fetches entire league dataset in one bulk call (~2 seconds)
    instead of per-player calls (549 × 1 second = 9 minutes).

    Cache expires after 24 hours (xG data doesn't change intra-day).
    """

    CACHE_DIR = Path("data/understat_cache")
    CACHE_EXPIRY_HOURS = 24

    def __init__(self, league: str = 'EPL', season: str = '2025'):
        """
        Initialize Understat client with bulk data fetching.

        Args:
            league: League code ('EPL', 'La_Liga', 'Bundesliga', etc.)
            season: Season year (e.g., '2025' for 2025/26 season)
        """
        self.league = league
        self.season = season
        self.CACHE_DIR.mkdir(parents=True, exist_ok=True)

        # Player lookup: player_name -> PlayerXGStats
        self._player_data: Dict[str, PlayerXGStats] = {}

        # Load from cache or fetch fresh
        self._initialize_data()

    def _get_cache_file(self) -> Path:
        """Get cache file path for current league/season."""
        return self.CACHE_DIR / f"{self.league}_{self.season}_players.json"

    def _is_cache_valid(self) -> bool:
        """Check if cache exists and is not expired."""
        cache_file = self._get_cache_file()

        if not cache_file.exists():
            return False

        # Check cache age
        cache_time = datetime.fromtimestamp(cache_file.stat().st_mtime)
        age = datetime.now() - cache_time

        return age < timedelta(hours=self.CACHE_EXPIRY_HOURS)

    def _load_from_cache(self) -> bool:
        """Load player data from cache. Returns True if successful."""
        cache_file = self._get_cache_file()

        try:
            with open(cache_file, 'r') as f:
                cached_data = json.load(f)

            # Reconstruct PlayerXGStats objects
            self._player_data = {
                name: PlayerXGStats(**data)
                for name, data in cached_data.items()
            }

            print(f"  ✓ Loaded {len(self._player_data)} players from Understat cache")
            return True
        except Exception as e:
            print(f"Warning: Could not load Understat cache: {e}")
            return False

    def _save_to_cache(self):
        """Save player data to cache."""
        cache_file = self._get_cache_file()

        try:
            # Convert to JSON-serializable format
            cache_data = {
                name: asdict(stats)
                for name, stats in self._player_data.items()
            }

            with open(cache_file, 'w') as f:
                json.dump(cache_data, f, indent=2)

            print(f"  ✓ Cached {len(self._player_data)} players to {cache_file}")
        except Exception as e:
            print(f"Warning: Could not save Understat cache: {e}")

    def _fetch_all_league_data(self) -> bool:
        """
        Fetch ALL player data for the league in one bulk call.

        This is the key optimization - one API call instead of 549!

        Returns:
            True if successful, False otherwise
        """
        try:
            # Import here to avoid dependency issues if not installed
            from understatapi import UnderstatClient as UClient

            print(f"  Fetching all {self.league} player data from Understat...")

            client = UClient()
            league_data = client.league(league=self.league).get_player_data(season=self.season)

            # Parse all players at once
            self._player_data = {}
            for player_data in league_data:
                stats = self._parse_player_data(player_data)
                # Store by lowercase name for case-insensitive lookup
                self._player_data[stats.player_name.lower()] = stats

            print(f"  ✓ Fetched {len(self._player_data)} players from Understat")

            # Save to cache
            self._save_to_cache()

            return True

        except ImportError:
            print("Warning: understatapi not installed. Run: pip install understatapi")
            return False
        except Exception as e:
            print(f"Warning: Could not fetch Understat data: {e}")
            return False

    def _initialize_data(self):
        """Initialize data from cache or fresh fetch."""
        # Try cache first
        if self._is_cache_valid():
            if self._load_from_cache():
                return

        # Cache miss or expired - fetch fresh
        print(f"\n  ⏳ Understat cache expired or missing - fetching fresh data...")
        self._fetch_all_league_data()

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

    def get_player_xg_stats(self, player_name: str) -> Optional[PlayerXGStats]:
        """
        Get real xG/xA stats for a player (from cached data).

        Args:
            player_name: Player's full name (e.g., "Mohamed Salah")

        Returns:
            PlayerXGStats with xG/xA data, or None if not found
        """
        # Case-insensitive lookup
        name_lower = player_name.lower()

        # Direct lookup
        if name_lower in self._player_data:
            return self._player_data[name_lower]

        # Try fuzzy matching (handle slight name differences)
        for cached_name, stats in self._player_data.items():
            if player_name.lower() in cached_name or cached_name in player_name.lower():
                return stats

        return None

    def get_all_players(self) -> List[PlayerXGStats]:
        """Get all player stats from cache."""
        return list(self._player_data.values())

    def get_top_xg_players(self, top_n: int = 20) -> List[PlayerXGStats]:
        """
        Get top players by xG.

        Args:
            top_n: Number of players to return

        Returns:
            List of PlayerXGStats sorted by xG
        """
        players = self.get_all_players()
        players.sort(key=lambda x: x.xG, reverse=True)
        return players[:top_n]

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
        value_picks = []

        for stats in self._player_data.values():
            if (stats.minutes >= min_minutes and
                stats.xG_variance <= xg_variance_threshold and
                stats.xG >= 1.0):  # At least some goal threat
                value_picks.append(stats)

        # Sort by underperformance (most underperforming first)
        value_picks.sort(key=lambda x: x.xG_variance)
        return value_picks[:15]  # Top 15 value picks

    def refresh_cache(self):
        """Force refresh of cached data from Understat API."""
        print(f"\n  🔄 Forcing refresh of Understat data...")
        self._fetch_all_league_data()

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
            'Bruno Fernandes': 'Bruno Fernandes',
            # Add more mappings as needed
        }

        return name_mappings.get(fpl_name, fpl_name)


# Singleton instance for caching across requests
_understat_client_instance = None


def get_understat_client(league: str = 'EPL', season: str = '2025') -> UnderstatClient:
    """
    Get singleton Understat client instance.

    Uses singleton pattern to ensure we only fetch league data once per session.
    """
    global _understat_client_instance
    if _understat_client_instance is None:
        _understat_client_instance = UnderstatClient(league=league, season=season)
    return _understat_client_instance
