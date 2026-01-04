"""
FPL API Client for fetching player data, fixtures, and team information.
"""
import requests
from typing import Dict, List, Optional
import time


class FPLAPIClient:
    """Client for interacting with the Fantasy Premier League API."""

    BASE_URL = "https://fantasy.premierleague.com/api"

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'FPL-Optimizer/1.0'
        })
        self._bootstrap_cache = None
        self._cache_timestamp = 0
        self.CACHE_TTL = 300  # 5 minutes

    def _get(self, endpoint: str) -> Dict:
        """Make GET request to FPL API with error handling."""
        url = f"{self.BASE_URL}/{endpoint}"
        try:
            response = self.session.get(url, timeout=10)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            raise Exception(f"Failed to fetch data from {url}: {str(e)}")

    def get_bootstrap_static(self, force_refresh: bool = False) -> Dict:
        """
        Get bootstrap-static data (all players, teams, gameweeks).
        This is cached for performance as it's the main data source.

        Returns:
            Dict containing 'elements' (players), 'teams', 'events' (gameweeks), etc.
        """
        current_time = time.time()

        if force_refresh or self._bootstrap_cache is None or \
           (current_time - self._cache_timestamp) > self.CACHE_TTL:
            self._bootstrap_cache = self._get("bootstrap-static/")
            self._cache_timestamp = current_time

        return self._bootstrap_cache

    def get_players(self) -> List[Dict]:
        """Get all player data."""
        data = self.get_bootstrap_static()
        return data['elements']

    def get_teams(self) -> List[Dict]:
        """Get all team data."""
        data = self.get_bootstrap_static()
        return data['teams']

    def get_gameweeks(self) -> List[Dict]:
        """Get all gameweek data."""
        data = self.get_bootstrap_static()
        return data['events']

    def get_current_gameweek(self) -> Optional[int]:
        """Get the current active gameweek number."""
        gameweeks = self.get_gameweeks()
        for gw in gameweeks:
            if gw['is_current']:
                return gw['id']

        # If no current, return next gameweek
        for gw in gameweeks:
            if gw['is_next']:
                return gw['id']

        return None

    def get_fixtures(self) -> List[Dict]:
        """Get all fixtures (past and future)."""
        return self._get("fixtures/")

    def get_upcoming_fixtures(self, num_gameweeks: int = 5) -> List[Dict]:
        """
        Get upcoming fixtures for the next N gameweeks.

        Args:
            num_gameweeks: Number of future gameweeks to fetch

        Returns:
            List of fixture dictionaries
        """
        current_gw = self.get_current_gameweek()
        if not current_gw:
            return []

        all_fixtures = self.get_fixtures()
        upcoming = [
            f for f in all_fixtures
            if f['event'] is not None and
            current_gw <= f['event'] < current_gw + num_gameweeks
        ]
        return upcoming

    def get_player_details(self, player_id: int) -> Dict:
        """Get detailed information for a specific player including history."""
        return self._get(f"element-summary/{player_id}/")

    def get_element_types(self) -> List[Dict]:
        """Get position type information (GK, DEF, MID, FWD)."""
        data = self.get_bootstrap_static()
        return data['element_types']
