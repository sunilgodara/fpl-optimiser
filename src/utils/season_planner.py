"""
Long-term season planning for FPL strategy (GW1-38 overview).
Helps with chip timing, fixture swings, and strategic milestones.
"""
from typing import Dict, List, Tuple
from ..data.models import GameweekData, Fixture


class SeasonPlanner:
    """
    Provides long-term season planning and strategic overview.

    Key features:
    - Fixture difficulty by team across season
    - Best wildcard windows
    - Chip timing recommendations
    - Double/blank gameweek identification
    - Strategic milestones
    """

    def __init__(self, gameweek_data: GameweekData):
        self.data = gameweek_data
        self._fixture_difficulty_by_team = None

    def get_fixture_difficulty_by_team(
        self,
        start_gw: int,
        end_gw: int
    ) -> Dict[int, List[Tuple[int, int]]]:
        """
        Get fixture difficulty rating for each team across gameweeks.

        Returns:
            Dict of {team_id: [(gameweek, difficulty), ...]}
        """
        if self._fixture_difficulty_by_team is None:
            self._fixture_difficulty_by_team = {}

            for team in self.data.teams:
                team_fixtures = []

                # Get all fixtures for this team
                for fixture in self.data.fixtures:
                    if fixture.event is None:
                        continue

                    if fixture.event < start_gw or fixture.event > end_gw:
                        continue

                    # Determine if home or away
                    if fixture.team_h == team.id:
                        difficulty = fixture.team_h_difficulty
                    elif fixture.team_a == team.id:
                        difficulty = fixture.team_a_difficulty
                    else:
                        continue

                    team_fixtures.append((fixture.event, difficulty))

                # Sort by gameweek
                team_fixtures.sort(key=lambda x: x[0])
                self._fixture_difficulty_by_team[team.id] = team_fixtures

        return self._fixture_difficulty_by_team

    def identify_best_fixture_runs(
        self,
        start_gw: int,
        end_gw: int,
        run_length: int = 5
    ) -> List[Dict]:
        """
        Identify teams with best upcoming fixture runs.

        Args:
            start_gw: Start gameweek
            end_gw: End gameweek
            run_length: Number of consecutive fixtures to analyze

        Returns:
            List of fixture run dicts sorted by quality
        """
        fixture_difficulty = self.get_fixture_difficulty_by_team(start_gw, end_gw)
        fixture_runs = []

        for team_id, fixtures in fixture_difficulty.items():
            team = self.data.get_team_by_id(team_id)
            if not team:
                continue

            # Find all runs of run_length fixtures
            for i in range(len(fixtures) - run_length + 1):
                run = fixtures[i:i + run_length]

                # Calculate average difficulty
                avg_difficulty = sum(f[1] for f in run) / len(run)

                # Calculate how many easy fixtures (1-2 difficulty)
                easy_fixtures = sum(1 for f in run if f[1] <= 2)

                fixture_runs.append({
                    'team': team.short_name,
                    'team_id': team_id,
                    'start_gw': run[0][0],
                    'end_gw': run[-1][0],
                    'avg_difficulty': avg_difficulty,
                    'easy_fixtures': easy_fixtures,
                    'fixtures': run,
                    'quality_score': easy_fixtures * 2 - avg_difficulty  # Higher = better
                })

        # Sort by quality score
        fixture_runs.sort(key=lambda x: x['quality_score'], reverse=True)

        return fixture_runs[:10]  # Top 10 fixture runs

    def identify_double_gameweeks(
        self,
        start_gw: int,
        end_gw: int
    ) -> Dict[int, List[int]]:
        """
        Identify double gameweeks (teams with 2+ fixtures in same GW).

        Returns:
            Dict of {gameweek: [team_ids with doubles]}
        """
        double_gameweeks = {}

        for gw in range(start_gw, end_gw + 1):
            # Count fixtures per team in this gameweek
            team_fixture_count = {}

            for fixture in self.data.fixtures:
                if fixture.event != gw:
                    continue

                team_fixture_count[fixture.team_h] = team_fixture_count.get(fixture.team_h, 0) + 1
                team_fixture_count[fixture.team_a] = team_fixture_count.get(fixture.team_a, 0) + 1

            # Find teams with 2+ fixtures
            teams_with_doubles = [
                team_id for team_id, count in team_fixture_count.items()
                if count >= 2
            ]

            if teams_with_doubles:
                double_gameweeks[gw] = teams_with_doubles

        return double_gameweeks

    def identify_blank_gameweeks(
        self,
        start_gw: int,
        end_gw: int
    ) -> Dict[int, List[int]]:
        """
        Identify blank gameweeks (teams with 0 fixtures in a GW).

        Returns:
            Dict of {gameweek: [team_ids with blanks]}
        """
        blank_gameweeks = {}

        all_team_ids = {team.id for team in self.data.teams}

        for gw in range(start_gw, end_gw + 1):
            # Find teams playing in this gameweek
            teams_playing = set()

            for fixture in self.data.fixtures:
                if fixture.event == gw:
                    teams_playing.add(fixture.team_h)
                    teams_playing.add(fixture.team_a)

            # Teams not playing = blank
            teams_with_blanks = list(all_team_ids - teams_playing)

            if teams_with_blanks:
                blank_gameweeks[gw] = teams_with_blanks

        return blank_gameweeks

    def suggest_wildcard_windows(
        self,
        start_gw: int,
        end_gw: int
    ) -> List[Dict]:
        """
        Suggest best gameweeks to use wildcard.

        Good wildcard timing:
        - Before a set of good fixture runs
        - After fixture difficulty changes
        - Before double gameweeks

        Returns:
            List of wildcard window recommendations
        """
        # Get best fixture runs
        fixture_runs = self.identify_best_fixture_runs(start_gw, end_gw, run_length=5)

        # Get double gameweeks
        double_gameweeks = self.identify_double_gameweeks(start_gw, end_gw)

        wildcard_windows = []

        # Recommend wildcarding 1-2 GWs before good fixture runs
        seen_gws = set()
        for run in fixture_runs[:5]:  # Top 5 fixture runs
            wildcard_gw = max(start_gw, run['start_gw'] - 1)

            if wildcard_gw in seen_gws:
                continue
            seen_gws.add(wildcard_gw)

            wildcard_windows.append({
                'gameweek': wildcard_gw,
                'reason': f"Before excellent {run['team']} fixture run (GW{run['start_gw']}-{run['end_gw']})",
                'avg_difficulty': run['avg_difficulty'],
                'priority': 'High' if run['easy_fixtures'] >= 4 else 'Medium'
            })

        # Recommend wildcarding before double gameweeks
        for dgw, teams in sorted(double_gameweeks.items()):
            if len(teams) >= 4:  # Multiple teams with doubles
                wildcard_gw = max(start_gw, dgw - 1)

                if wildcard_gw not in seen_gws:
                    seen_gws.add(wildcard_gw)
                    team_names = [self.data.get_team_by_id(tid).short_name for tid in teams[:3]]

                    wildcard_windows.append({
                        'gameweek': wildcard_gw,
                        'reason': f"Before DGW{dgw} ({', '.join(team_names)}+)",
                        'avg_difficulty': 2.0,  # Doubles are generally good regardless
                        'priority': 'Very High'
                    })

        # Sort by priority and gameweek
        priority_order = {'Very High': 0, 'High': 1, 'Medium': 2}
        wildcard_windows.sort(key=lambda x: (priority_order.get(x['priority'], 3), x['gameweek']))

        return wildcard_windows[:5]  # Top 5 wildcard windows

    def get_season_overview(
        self,
        current_gw: int,
        horizon: int = 16  # Rest of season from current GW
    ) -> Dict:
        """
        Get comprehensive season overview.

        Returns:
            Dict with season planning information
        """
        end_gw = min(38, current_gw + horizon)

        return {
            'current_gameweek': current_gw,
            'planning_horizon': f"GW{current_gw}-GW{end_gw}",
            'best_fixture_runs': self.identify_best_fixture_runs(current_gw, end_gw, run_length=5),
            'double_gameweeks': self.identify_double_gameweeks(current_gw, end_gw),
            'blank_gameweeks': self.identify_blank_gameweeks(current_gw, end_gw),
            'wildcard_windows': self.suggest_wildcard_windows(current_gw, end_gw),
        }
