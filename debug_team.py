"""
Debug script to inspect FPL API responses for team data.
Run this to see what data is available in the API responses.
"""
import sys
from src.data.api_client import FPLAPIClient
import json

def debug_team_data(team_id: int):
    """Fetch and print all team-related API responses."""
    print("=" * 80)
    print(f"FPL API Debug - Team ID: {team_id}")
    print("=" * 80)

    client = FPLAPIClient()

    # Get current gameweek
    current_gw = client.get_current_gameweek()
    print(f"\nCurrent Gameweek: {current_gw}")

    # Fetch team info
    print("\n" + "=" * 80)
    print("1. TEAM INFO (entry/{team_id}/)")
    print("=" * 80)
    try:
        team_info = client.get_team_info(team_id)
        print(json.dumps(team_info, indent=2))
    except Exception as e:
        print(f"Error: {e}")

    # Fetch picks
    print("\n" + "=" * 80)
    print(f"2. TEAM PICKS (entry/{team_id}/event/{current_gw}/picks/)")
    print("=" * 80)
    try:
        picks_data = client.get_team_picks(team_id, current_gw)
        print(json.dumps(picks_data, indent=2))
    except Exception as e:
        print(f"Error: {e}")

    # Fetch transfers
    print("\n" + "=" * 80)
    print(f"3. TEAM TRANSFERS (entry/{team_id}/transfers/)")
    print("=" * 80)
    try:
        transfers_data = client.get_team_transfers(team_id)
        print(json.dumps(transfers_data, indent=2))
    except Exception as e:
        print(f"Error: {e}")

    print("\n" + "=" * 80)
    print("Debug complete!")
    print("=" * 80)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python debug_team.py <team_id>")
        print("Example: python debug_team.py 450211")
        sys.exit(1)

    team_id = int(sys.argv[1])
    debug_team_data(team_id)
