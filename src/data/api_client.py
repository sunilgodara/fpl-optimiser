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

    def get_team_info(self, team_id: int) -> Dict:
        """
        Get information about a specific FPL team.

        Args:
            team_id: The FPL team ID

        Returns:
            Dict with team information including name, rank, points, etc.
        """
        return self._get(f"entry/{team_id}/")

    def get_team_picks(self, team_id: int, gameweek: Optional[int] = None) -> Dict:
        """
        Get the squad picks for a specific FPL team in a gameweek.

        Args:
            team_id: The FPL team ID
            gameweek: The gameweek number (uses current if None)

        Returns:
            Dict with picks, transfers, and chips information
        """
        if gameweek is None:
            gameweek = self.get_current_gameweek()

        return self._get(f"entry/{team_id}/event/{gameweek}/picks/")

    def get_team_current_squad(self, team_id: int) -> Dict:
        """
        Get the current squad for an FPL team.

        Returns:
            Dict with 'squad' (list of player IDs), 'bank' (money remaining),
            'squad_value', 'free_transfers'
        """
        current_gw = self.get_current_gameweek()
        if not current_gw:
            return None

        try:
            # Get team info for bank and value
            team_info = self.get_team_info(team_id)

            # Get current picks
            picks_data = self.get_team_picks(team_id, current_gw)

            # Extract squad (all 15 players)
            squad = [pick['element'] for pick in picks_data['picks']]

            # Get transfer info
            transfers = picks_data.get('entry_history', {})

            return {
                'squad': squad,
                'bank': team_info['last_deadline_bank'] / 10.0,  # Convert from tenths
                'squad_value': team_info['last_deadline_value'] / 10.0,
                'free_transfers': transfers.get('event_transfers', 1),
                'total_points': team_info['summary_overall_points'],
                'overall_rank': team_info['summary_overall_rank'],
                'team_name': team_info['name'],
                'player_name': f"{team_info['player_first_name']} {team_info['player_last_name']}"
            }
        except Exception as e:
            print(f"Warning: Could not fetch team data: {str(e)}")
            return None
