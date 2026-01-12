"""
Squad optimizer using linear programming to maximize expected points
while respecting all FPL constraints.
"""
import pulp
from typing import Dict, List, Optional, Tuple
from ..data.models import Player, GameweekData


class SquadOptimizer:
    """Optimizes FPL squad selection using linear programming."""

    # Squad constraints
    SQUAD_SIZE = 15
    BUDGET = 100.0  # £100m

    # Position requirements
    NUM_GOALKEEPERS = 2
    NUM_DEFENDERS = 5
    NUM_MIDFIELDERS = 5
    NUM_FORWARDS = 3

    # Team constraint
    MAX_PLAYERS_PER_TEAM = 3

    # Starting XI constraints
    STARTING_XI_SIZE = 11
    STARTING_GK = 1
    MIN_STARTING_DEF = 3
    MAX_STARTING_DEF = 5
    MIN_STARTING_MID = 2
    MAX_STARTING_MID = 5
    MIN_STARTING_FWD = 1
    MAX_STARTING_FWD = 3

    def __init__(self, gameweek_data: GameweekData):
        self.data = gameweek_data
        self.players = self.data.get_available_players()

    def optimize_squad(
        self,
        expected_points: Dict[int, float],
        verbose: bool = True,
        bench_weight: float = 0.1
    ) -> Optional[Dict]:
        """
        Optimize squad selection to maximize expected points with bench fodder strategy.

        The optimizer now prioritizes a strong starting XI with cheap bench players,
        rather than spreading budget evenly across all 15 players.

        Args:
            expected_points: Dict mapping player_id -> expected_points
            verbose: Print optimization details
            bench_weight: Weight for bench players (0.1 = bench players worth 10% of starters)

        Returns:
            Dict with 'squad' (list of player IDs) and 'total_expected_points'
            or None if optimization failed
        """
        # Create optimization problem
        prob = pulp.LpProblem("FPL_Squad_Selection", pulp.LpMaximize)

        # Decision variables: 1 if player is selected, 0 otherwise
        player_vars = {
            player.id: pulp.LpVariable(f"player_{player.id}", cat='Binary')
            for player in self.players
        }

        # Bench fodder strategy: Weight players by their likelihood of starting
        # For each position, estimate starting likelihood based on EP ranking
        position_weights = {}

        for position in ['GK', 'DEF', 'MID', 'FWD']:
            position_players = [p for p in self.players if p.position == position]
            # Sort by expected points
            sorted_players = sorted(
                position_players,
                key=lambda p: expected_points.get(p.id, 0),
                reverse=True
            )

            # Assign weights based on ranking within position
            # Starters: 1.0x weight, Bench: bench_weight (e.g., 0.1x)
            starters_needed = {
                'GK': 1,   # 1 GK plays
                'DEF': 5,  # Up to 5 DEF can play
                'MID': 5,  # Up to 5 MID can play
                'FWD': 3   # Up to 3 FWD can play
            }[position]

            for idx, player in enumerate(sorted_players):
                # Top players in position get full weight, rest get bench_weight
                if idx < starters_needed:
                    position_weights[player.id] = 1.0
                else:
                    position_weights[player.id] = bench_weight

        # Objective: Maximize weighted expected points (prioritizes strong starting XI)
        prob += pulp.lpSum([
            expected_points.get(player.id, 0) * position_weights.get(player.id, 1.0) * player_vars[player.id]
            for player in self.players
        ]), "Weighted_Expected_Points"

        # Constraint 1: Squad size = 15
        prob += pulp.lpSum([
            player_vars[player.id] for player in self.players
        ]) == self.SQUAD_SIZE, "Squad_Size"

        # Constraint 2: Budget <= 100m
        prob += pulp.lpSum([
            player.price * player_vars[player.id]
            for player in self.players
        ]) <= self.BUDGET, "Budget"

        # Constraint 3: Position requirements
        players_by_position = {
            'GK': [p for p in self.players if p.position == 'GK'],
            'DEF': [p for p in self.players if p.position == 'DEF'],
            'MID': [p for p in self.players if p.position == 'MID'],
            'FWD': [p for p in self.players if p.position == 'FWD'],
        }

        prob += pulp.lpSum([
            player_vars[p.id] for p in players_by_position['GK']
        ]) == self.NUM_GOALKEEPERS, "Num_Goalkeepers"

        prob += pulp.lpSum([
            player_vars[p.id] for p in players_by_position['DEF']
        ]) == self.NUM_DEFENDERS, "Num_Defenders"

        prob += pulp.lpSum([
            player_vars[p.id] for p in players_by_position['MID']
        ]) == self.NUM_MIDFIELDERS, "Num_Midfielders"

        prob += pulp.lpSum([
            player_vars[p.id] for p in players_by_position['FWD']
        ]) == self.NUM_FORWARDS, "Num_Forwards"

        # Constraint 4: Max 3 players per team
        teams = set(p.team_id for p in self.players)
        for team_id in teams:
            team_players = [p for p in self.players if p.team_id == team_id]
            prob += pulp.lpSum([
                player_vars[p.id] for p in team_players
            ]) <= self.MAX_PLAYERS_PER_TEAM, f"Max_Players_Team_{team_id}"

        # Solve
        prob.solve(pulp.PULP_CBC_CMD(msg=0))

        # Check if solution found
        if prob.status != pulp.LpStatusOptimal:
            if verbose:
                print(f"Optimization failed with status: {pulp.LpStatus[prob.status]}")
            return None

        # Extract selected players
        selected_player_ids = [
            player.id for player in self.players
            if player_vars[player.id].varValue == 1
        ]

        total_points = pulp.value(prob.objective)
        total_cost = sum(
            self.data.get_player_by_id(pid).price
            for pid in selected_player_ids
        )

        if verbose:
            print(f"\nSquad optimized successfully!")
            print(f"Total expected points: {total_points:.2f}")
            print(f"Total cost: £{total_cost:.1f}m")

        return {
            'squad': selected_player_ids,
            'total_expected_points': total_points,
            'total_cost': total_cost
        }

    def optimize_starting_xi(
        self,
        squad_player_ids: List[int],
        expected_points: Dict[int, float],
        verbose: bool = True
    ) -> Optional[Dict]:
        """
        Optimize starting XI selection from squad.

        Args:
            squad_player_ids: List of player IDs in the squad
            expected_points: Dict mapping player_id -> expected_points
            verbose: Print optimization details

        Returns:
            Dict with 'starting_xi' (list of player IDs), 'captain' (player_id),
            and 'total_expected_points', or None if optimization failed
        """
        squad_players = [
            self.data.get_player_by_id(pid) for pid in squad_player_ids
        ]

        # Create optimization problem
        prob = pulp.LpProblem("FPL_Starting_XI", pulp.LpMaximize)

        # Decision variables
        starting_vars = {
            player.id: pulp.LpVariable(f"start_{player.id}", cat='Binary')
            for player in squad_players
        }

        captain_vars = {
            player.id: pulp.LpVariable(f"captain_{player.id}", cat='Binary')
            for player in squad_players
        }

        # Objective: Maximize expected points (captain gets 2x points)
        prob += pulp.lpSum([
            expected_points.get(player.id, 0) * starting_vars[player.id] +
            expected_points.get(player.id, 0) * captain_vars[player.id]  # Captain bonus
            for player in squad_players
        ]), "Total_Points_With_Captain"

        # Constraint 1: Starting XI size = 11
        prob += pulp.lpSum([
            starting_vars[player.id] for player in squad_players
        ]) == self.STARTING_XI_SIZE, "Starting_XI_Size"

        # Constraint 2: Exactly 1 captain
        prob += pulp.lpSum([
            captain_vars[player.id] for player in squad_players
        ]) == 1, "One_Captain"

        # Constraint 3: Captain must be in starting XI
        for player in squad_players:
            prob += captain_vars[player.id] <= starting_vars[player.id], \
                f"Captain_In_XI_{player.id}"

        # Constraint 4: Valid formation
        squad_by_position = {
            'GK': [p for p in squad_players if p.position == 'GK'],
            'DEF': [p for p in squad_players if p.position == 'DEF'],
            'MID': [p for p in squad_players if p.position == 'MID'],
            'FWD': [p for p in squad_players if p.position == 'FWD'],
        }

        # Exactly 1 GK
        prob += pulp.lpSum([
            starting_vars[p.id] for p in squad_by_position['GK']
        ]) == self.STARTING_GK, "Starting_GK"

        # 3-5 DEF
        prob += pulp.lpSum([
            starting_vars[p.id] for p in squad_by_position['DEF']
        ]) >= self.MIN_STARTING_DEF, "Min_Starting_DEF"
        prob += pulp.lpSum([
            starting_vars[p.id] for p in squad_by_position['DEF']
        ]) <= self.MAX_STARTING_DEF, "Max_Starting_DEF"

        # 2-5 MID
        prob += pulp.lpSum([
            starting_vars[p.id] for p in squad_by_position['MID']
        ]) >= self.MIN_STARTING_MID, "Min_Starting_MID"
        prob += pulp.lpSum([
            starting_vars[p.id] for p in squad_by_position['MID']
        ]) <= self.MAX_STARTING_MID, "Max_Starting_MID"

        # 1-3 FWD
        prob += pulp.lpSum([
            starting_vars[p.id] for p in squad_by_position['FWD']
        ]) >= self.MIN_STARTING_FWD, "Min_Starting_FWD"
        prob += pulp.lpSum([
            starting_vars[p.id] for p in squad_by_position['FWD']
        ]) <= self.MAX_STARTING_FWD, "Max_Starting_FWD"

        # Solve
        prob.solve(pulp.PULP_CBC_CMD(msg=0))

        if prob.status != pulp.LpStatusOptimal:
            if verbose:
                print(f"Starting XI optimization failed: {pulp.LpStatus[prob.status]}")
            return None

        # Extract results
        starting_xi = [
            player.id for player in squad_players
            if starting_vars[player.id].varValue == 1
        ]

        captain_id = None
        for player in squad_players:
            if captain_vars[player.id].varValue == 1:
                captain_id = player.id
                break

        total_points = pulp.value(prob.objective)

        if verbose:
            captain = self.data.get_player_by_id(captain_id)
            print(f"\nStarting XI optimized successfully!")
            print(f"Captain: {captain.name}")
            print(f"Total expected points: {total_points:.2f}")

        return {
            'starting_xi': starting_xi,
            'captain': captain_id,
            'total_expected_points': total_points
        }

    def display_squad(
        self,
        squad_player_ids: List[int],
        expected_points: Dict[int, float],
        starting_xi: Optional[List[int]] = None,
        captain_id: Optional[int] = None
    ):
        """Display squad in a readable format."""
        squad_players = [self.data.get_player_by_id(pid) for pid in squad_player_ids]

        # Group by position
        by_position = {
            'GK': [],
            'DEF': [],
            'MID': [],
            'FWD': []
        }

        for player in squad_players:
            by_position[player.position].append(player)

        # Sort by expected points within each position
        for position in by_position:
            by_position[position].sort(
                key=lambda p: expected_points.get(p.id, 0),
                reverse=True
            )

        print("\n" + "="*80)
        print("OPTIMIZED SQUAD")
        print("="*80)

        for position in ['GK', 'DEF', 'MID', 'FWD']:
            print(f"\n{position}:")
            print("-" * 80)
            for player in by_position[position]:
                team = self.data.get_team_by_id(player.team_id)
                ep = expected_points.get(player.id, 0)
                status = ""

                if starting_xi and player.id in starting_xi:
                    status = " [STARTING]"
                    if captain_id and player.id == captain_id:
                        status = " [CAPTAIN]"

                print(f"  {player.name:20} | {team.short_name:4} | "
                      f"£{player.price:4.1f}m | EP: {ep:5.2f}{status}")

        print("="*80)
