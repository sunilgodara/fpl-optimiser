"""
Data models for FPL entities.
"""
from dataclasses import dataclass
from typing import List, Optional, Dict


@dataclass
class Player:
    """Represents an FPL player."""
    id: int
    name: str
    team_id: int
    position: str  # GK, DEF, MID, FWD
    price: float  # In millions (e.g., 10.5)
    total_points: int
    points_per_game: float
    form: float
    selected_by_percent: float
    minutes: int
    goals_scored: int
    assists: int
    clean_sheets: int
    goals_conceded: int
    bonus: int
    status: str  # a = available, d = doubtful, i = injured, u = unavailable
    chance_of_playing_next_round: Optional[int]
    ep_next: Optional[float]  # Expected points next gameweek (from FPL)
    ep_this: Optional[float]

    @classmethod
    def from_api_data(cls, data: Dict, element_types: Dict[int, str]) -> 'Player':
        """Create Player from FPL API element data."""
        return cls(
            id=data['id'],
            name=data['web_name'],
            team_id=data['team'],
            position=element_types[data['element_type']],
            price=data['now_cost'] / 10.0,  # API returns in tenths
            total_points=data['total_points'],
            points_per_game=float(data['points_per_game']),
            form=float(data['form']),
            selected_by_percent=float(data['selected_by_percent']),
            minutes=data['minutes'],
            goals_scored=data['goals_scored'],
            assists=data['assists'],
            clean_sheets=data['clean_sheets'],
            goals_conceded=data['goals_conceded'],
            bonus=data['bonus'],
            status=data['status'],
            chance_of_playing_next_round=data['chance_of_playing_next_round'],
            ep_next=float(data['ep_next']) if data['ep_next'] else None,
            ep_this=float(data['ep_this']) if data['ep_this'] else None,
        )

    def is_available(self) -> bool:
        """Check if player is available for selection."""
        if self.status in ['i', 'u', 's']:  # injured, unavailable, suspended
            return False
        if self.chance_of_playing_next_round is not None and \
           self.chance_of_playing_next_round < 50:
            return False
        return True


@dataclass
class Team:
    """Represents an FPL team (Premier League club)."""
    id: int
    name: str
    short_name: str
    strength: int
    strength_overall_home: int
    strength_overall_away: int
    strength_attack_home: int
    strength_attack_away: int
    strength_defence_home: int
    strength_defence_away: int

    @classmethod
    def from_api_data(cls, data: Dict) -> 'Team':
        """Create Team from FPL API team data."""
        return cls(
            id=data['id'],
            name=data['name'],
            short_name=data['short_name'],
            strength=data['strength'],
            strength_overall_home=data['strength_overall_home'],
            strength_overall_away=data['strength_overall_away'],
            strength_attack_home=data['strength_attack_home'],
            strength_attack_away=data['strength_attack_away'],
            strength_defence_home=data['strength_defence_home'],
            strength_defence_away=data['strength_defence_away'],
        )


@dataclass
class Fixture:
    """Represents a Premier League fixture."""
    id: int
    event: Optional[int]  # Gameweek number
    team_h: int  # Home team ID
    team_a: int  # Away team ID
    team_h_difficulty: int  # 1-5, higher = harder
    team_a_difficulty: int
    finished: bool
    kickoff_time: str

    @classmethod
    def from_api_data(cls, data: Dict) -> 'Fixture':
        """Create Fixture from FPL API fixture data."""
        return cls(
            id=data['id'],
            event=data['event'],
            team_h=data['team_h'],
            team_a=data['team_a'],
            team_h_difficulty=data['team_h_difficulty'],
            team_a_difficulty=data['team_a_difficulty'],
            finished=data['finished'],
            kickoff_time=data['kickoff_time'],
        )


@dataclass
class GameweekData:
    """Container for all gameweek-related data."""
    players: List[Player]
    teams: Dict[int, Team]
    fixtures: List[Fixture]
    current_gameweek: int

    def get_player_by_id(self, player_id: int) -> Optional[Player]:
        """Get player by ID."""
        for player in self.players:
            if player.id == player_id:
                return player
        return None

    def get_team_by_id(self, team_id: int) -> Optional[Team]:
        """Get team by ID."""
        return self.teams.get(team_id)

    def get_available_players(self) -> List[Player]:
        """Get all available players (not injured/suspended)."""
        return [p for p in self.players if p.is_available()]


def build_gameweek_data(api_client) -> GameweekData:
    """
    Build GameweekData from API client.

    Args:
        api_client: FPLAPIClient instance

    Returns:
        GameweekData with all current data
    """
    # Get element types mapping
    element_types_data = api_client.get_element_types()
    element_types_map = {et['id']: et['singular_name_short'] for et in element_types_data}

    # Build players
    players_data = api_client.get_players()
    players = [Player.from_api_data(p, element_types_map) for p in players_data]

    # Build teams
    teams_data = api_client.get_teams()
    teams = {t['id']: Team.from_api_data(t) for t in teams_data}

    # Build fixtures
    fixtures_data = api_client.get_upcoming_fixtures(num_gameweeks=5)
    fixtures = [Fixture.from_api_data(f) for f in fixtures_data]

    # Get current gameweek
    current_gw = api_client.get_current_gameweek()

    return GameweekData(
        players=players,
        teams=teams,
        fixtures=fixtures,
        current_gameweek=current_gw or 1
    )
