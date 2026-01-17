"""
Historical data collector for backtesting FPL strategies.

Fetches past season data from FPL API for validation.
"""
import json
import time
from typing import Dict, List, Optional
from pathlib import Path
import requests


class HistoricalDataCollector:
    """
    Collects historical FPL data for backtesting.

    Uses FPL API endpoints to fetch:
    - Player gameweek scores (actual points)
    - Fixtures and results
    - Ownership data
    - Prices at each gameweek
    """

    BASE_URL = "https://fantasy.premierleague.com/api"
    CACHE_DIR = Path("data/historical")

    def __init__(self, season: str = "2024-25"):
        """
        Initialize collector.

        Args:
            season: Season to collect (e.g., "2024-25", "2023-24")
        """
        self.season = season
        self.cache_dir = self.CACHE_DIR / season
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def fetch_bootstrap_static(self) -> Dict:
        """
        Fetch bootstrap-static data (players, teams, gameweeks).

        This is the main data snapshot. For historical seasons,
        this gives us the final state, but we need gameweek-by-gameweek
        data for proper backtesting.
        """
        cache_file = self.cache_dir / "bootstrap-static.json"

        if cache_file.exists():
            print(f"Loading cached bootstrap-static data...")
            with open(cache_file) as f:
                return json.load(f)

        print(f"Fetching bootstrap-static data...")
        response = requests.get(f"{self.BASE_URL}/bootstrap-static/")
        response.raise_for_status()
        data = response.json()

        # Cache it
        with open(cache_file, 'w') as f:
            json.dump(data, f, indent=2)

        return data

    def fetch_player_gameweek_history(self, player_id: int) -> List[Dict]:
        """
        Fetch gameweek-by-gameweek history for a player.

        Args:
            player_id: FPL player ID

        Returns:
            List of gameweek performance dicts
        """
        cache_file = self.cache_dir / f"player_{player_id}_history.json"

        if cache_file.exists():
            with open(cache_file) as f:
                return json.load(f)

        print(f"Fetching history for player {player_id}...")
        time.sleep(0.5)  # Rate limiting

        try:
            response = requests.get(f"{self.BASE_URL}/element-summary/{player_id}/")
            response.raise_for_status()
            data = response.json()

            history = data.get('history', [])

            # Cache it
            with open(cache_file, 'w') as f:
                json.dump(history, f, indent=2)

            return history
        except Exception as e:
            print(f"Warning: Could not fetch history for player {player_id}: {e}")
            return []

    def fetch_gameweek_live_data(self, gameweek: int) -> Dict:
        """
        Fetch live data for a specific gameweek (player scores, bonus, etc.).

        Args:
            gameweek: Gameweek number (1-38)

        Returns:
            Dict with live gameweek data
        """
        cache_file = self.cache_dir / f"gw_{gameweek}_live.json"

        if cache_file.exists():
            with open(cache_file) as f:
                return json.load(f)

        print(f"Fetching live data for GW{gameweek}...")
        time.sleep(0.5)  # Rate limiting

        try:
            response = requests.get(f"{self.BASE_URL}/event/{gameweek}/live/")
            response.raise_for_status()
            data = response.json()

            # Cache it
            with open(cache_file, 'w') as f:
                json.dump(data, f, indent=2)

            return data
        except Exception as e:
            print(f"Warning: Could not fetch live data for GW{gameweek}: {e}")
            return {}

    def build_historical_dataset(
        self,
        start_gw: int = 1,
        end_gw: int = 38
    ) -> Dict:
        """
        Build complete historical dataset for backtesting.

        Args:
            start_gw: Starting gameweek
            end_gw: Ending gameweek

        Returns:
            Dict with structured historical data:
            {
                'players': {...},  # Player metadata
                'gameweeks': {
                    1: {
                        'actual_points': {player_id: points},
                        'ownership': {player_id: percent},
                        'prices': {player_id: price}
                    },
                    ...
                }
            }
        """
        print("=" * 80)
        print(f"BUILDING HISTORICAL DATASET: {self.season}")
        print(f"Gameweeks {start_gw} to {end_gw}")
        print("=" * 80)

        # Fetch bootstrap data
        bootstrap = self.fetch_bootstrap_static()

        players = {}
        for player in bootstrap['elements']:
            players[player['id']] = {
                'name': f"{player['first_name']} {player['second_name']}",
                'position': ['GK', 'DEF', 'MID', 'FWD'][player['element_type'] - 1],
                'team': player['team'],
                'initial_price': player['now_cost'] / 10.0
            }

        print(f"\nLoaded {len(players)} players")

        # Build gameweek data
        gameweeks = {}

        for gw in range(start_gw, end_gw + 1):
            print(f"\nProcessing GW{gw}...")

            # Fetch live data for this gameweek
            live_data = self.fetch_gameweek_live_data(gw)

            if not live_data or 'elements' not in live_data:
                print(f"  Warning: No live data for GW{gw}")
                continue

            gw_data = {
                'actual_points': {},
                'ownership': {},
                'prices': {},
                'minutes': {},
                'bonus': {},
                'goals': {},
                'assists': {}
            }

            # Extract actual points and stats
            for element in live_data['elements']:
                player_id = element['id']
                stats = element['stats']

                gw_data['actual_points'][player_id] = stats['total_points']
                gw_data['minutes'][player_id] = stats['minutes']
                gw_data['bonus'][player_id] = stats['bonus']
                gw_data['goals'][player_id] = stats['goals_scored']
                gw_data['assists'][player_id] = stats['assists']

            # Get ownership and prices from bootstrap
            # Note: This gives us current ownership, not historical
            # For true historical ownership, we'd need archived data
            for player in bootstrap['elements']:
                player_id = player['id']
                gw_data['ownership'][player_id] = player['selected_by_percent']
                gw_data['prices'][player_id] = player['now_cost'] / 10.0

            gameweeks[gw] = gw_data
            print(f"  ✓ Collected data for {len(gw_data['actual_points'])} players")

        dataset = {
            'season': self.season,
            'players': players,
            'gameweeks': gameweeks,
            'metadata': {
                'start_gw': start_gw,
                'end_gw': end_gw,
                'total_gameweeks': len(gameweeks)
            }
        }

        # Save complete dataset
        output_file = self.cache_dir / "complete_dataset.json"
        with open(output_file, 'w') as f:
            json.dump(dataset, f, indent=2)

        print(f"\n✓ Dataset saved to {output_file}")
        print(f"  Total gameweeks: {len(gameweeks)}")
        print(f"  Total players: {len(players)}")

        return dataset

    def quick_collect(self, gameweeks: List[int]) -> Dict:
        """
        Quick collection for specific gameweeks (for testing).

        Args:
            gameweeks: List of gameweek numbers to collect

        Returns:
            Partial dataset with specified gameweeks
        """
        print(f"Quick collection for GWs: {gameweeks}")

        bootstrap = self.fetch_bootstrap_static()

        dataset = {
            'season': self.season,
            'players': {},
            'gameweeks': {},
            'metadata': {'quick_collection': True}
        }

        for player in bootstrap['elements']:
            dataset['players'][player['id']] = {
                'name': f"{player['first_name']} {player['second_name']}",
                'position': ['GK', 'DEF', 'MID', 'FWD'][player['element_type'] - 1],
                'team': player['team']
            }

        for gw in gameweeks:
            live_data = self.fetch_gameweek_live_data(gw)
            if live_data and 'elements' in live_data:
                gw_data = {'actual_points': {}}
                for element in live_data['elements']:
                    gw_data['actual_points'][element['id']] = element['stats']['total_points']
                dataset['gameweeks'][gw] = gw_data

        return dataset


def main():
    """Example usage: Collect historical data."""
    import argparse

    parser = argparse.ArgumentParser(description='Collect historical FPL data')
    parser.add_argument('--season', default='2024-25', help='Season (e.g., 2024-25)')
    parser.add_argument('--start-gw', type=int, default=1, help='Start gameweek')
    parser.add_argument('--end-gw', type=int, default=20, help='End gameweek')
    parser.add_argument('--quick', action='store_true', help='Quick collection (first 5 GWs)')

    args = parser.parse_args()

    collector = HistoricalDataCollector(season=args.season)

    if args.quick:
        dataset = collector.quick_collect([1, 2, 3, 4, 5])
    else:
        dataset = collector.build_historical_dataset(
            start_gw=args.start_gw,
            end_gw=args.end_gw
        )

    print("\n" + "=" * 80)
    print("COLLECTION COMPLETE!")
    print("=" * 80)
    print(f"Data saved to: data/historical/{args.season}/")


if __name__ == "__main__":
    main()
