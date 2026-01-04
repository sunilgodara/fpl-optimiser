"""
Basic tests for the FPL optimizer.
"""
import pytest
from src.data.models import Player, Team


def test_player_availability():
    """Test player availability logic."""
    # Available player
    player = Player(
        id=1, name="Test Player", team_id=1, position="MID",
        price=10.0, total_points=100, points_per_game=5.0,
        form=6.0, selected_by_percent=20.0, minutes=900,
        goals_scored=5, assists=3, clean_sheets=0,
        goals_conceded=10, bonus=10, status='a',
        chance_of_playing_next_round=100,
        ep_next=6.0, ep_this=6.0
    )
    assert player.is_available() is True

    # Injured player
    player.status = 'i'
    assert player.is_available() is False

    # Doubtful player
    player.status = 'd'
    player.chance_of_playing_next_round = 25
    assert player.is_available() is False

    player.chance_of_playing_next_round = 75
    assert player.is_available() is True


def test_team_creation():
    """Test team model creation."""
    team_data = {
        'id': 1,
        'name': 'Arsenal',
        'short_name': 'ARS',
        'strength': 4,
        'strength_overall_home': 1300,
        'strength_overall_away': 1250,
        'strength_attack_home': 1350,
        'strength_attack_away': 1300,
        'strength_defence_home': 1300,
        'strength_defence_away': 1250,
    }

    team = Team.from_api_data(team_data)
    assert team.id == 1
    assert team.name == 'Arsenal'
    assert team.short_name == 'ARS'
