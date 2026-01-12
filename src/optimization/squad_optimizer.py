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

    def get_captaincy_options(
        self,
        squad_player_ids: List[int],
        expected_points: Dict[int, float],
        num_options: int = 3
    ) -> List[Dict]:
        """
        Get top captaincy options with detailed reasoning.

        Provides 2-3 captain choices with analysis of:
        - Expected points (ceiling)
        - Consistency (floor/reliability)
        - Fixture quality
        - Risk profile (safe vs differential)

        Args:
            squad_player_ids: List of player IDs in squad
            expected_points: Dict mapping player_id -> expected_points
            num_options: Number of captain options to return (default 3)

        Returns:
            List of captain option dicts with reasoning
        """
        squad_players = [self.data.get_player_by_id(pid) for pid in squad_player_ids]

        # Calculate captain metrics for each player
        captain_candidates = []

        for player in squad_players:
            ep = expected_points.get(player.id, 0)

            # Skip low EP players
            if ep < 3.0:
                continue

            # Calculate consistency score from form variance
            # High form = consistent, low variance in recent scores
            consistency = min(player.form / max(ep, 1.0), 1.0) if ep > 0 else 0
            consistency = max(0.5, consistency)  # Clamp between 0.5 and 1.0

            # Calculate fixture quality (from recent games if available)
            # Use points_per_game as proxy for fixture quality
            fixture_score = min(player.points_per_game / 6.0, 1.0)  # Normalize to 1.0

            # Risk profile: high EP + low consistency = differential (risky)
            #               moderate EP + high consistency = safe
            if ep >= 8.0 and consistency < 0.7:
                risk_profile = "Differential"
                risk_color = "🎯"
            elif ep >= 6.0 and consistency >= 0.75:
                risk_profile = "Safe"
                risk_color = "🛡️"
            else:
                risk_profile = "Balanced"
                risk_color = "⚖️"

            # Overall captain score (weighted)
            captain_score = (
                ep * 0.50 +                    # 50% expected points
                (ep * consistency) * 0.30 +    # 30% reliability (EP * consistency)
                (ep * fixture_score) * 0.20    # 20% fixture quality
            )

            team = self.data.get_team_by_id(player.team_id)

            captain_candidates.append({
                'player_id': player.id,
                'name': player.name,
                'team': team.short_name if team else 'UNK',
                'position': player.position,
                'expected_points': ep,
                'consistency': consistency,
                'fixture_score': fixture_score,
                'risk_profile': risk_profile,
                'risk_color': risk_color,
                'captain_score': captain_score,
                'ownership': player.selected_by_percent,
                'form': player.form,
                'ppg': player.points_per_game
            })

        # Sort by captain score
        captain_candidates.sort(key=lambda x: x['captain_score'], reverse=True)

        # Generate reasoning for top N options
        options = []
        for i, candidate in enumerate(captain_candidates[:num_options]):
            # Build reasoning based on metrics
            reasons = []

            # Expected points
            if candidate['expected_points'] >= 8.0:
                reasons.append(f"Very high ceiling ({candidate['expected_points']:.1f} EP)")
            elif candidate['expected_points'] >= 6.0:
                reasons.append(f"Good expected points ({candidate['expected_points']:.1f} EP)")
            else:
                reasons.append(f"Moderate expected points ({candidate['expected_points']:.1f} EP)")

            # Consistency
            if candidate['consistency'] >= 0.80:
                reasons.append("Very consistent (high floor)")
            elif candidate['consistency'] >= 0.65:
                reasons.append("Reliable performer")
            else:
                reasons.append("Boom-or-bust potential")

            # Ownership
            if candidate['ownership'] < 10.0:
                reasons.append(f"Low ownership ({candidate['ownership']:.1f}%) - big differential!")
            elif candidate['ownership'] < 30.0:
                reasons.append(f"Moderate ownership ({candidate['ownership']:.1f}%)")
            else:
                reasons.append(f"Template pick ({candidate['ownership']:.1f}% owned)")

            # Form
            if candidate['form'] > 6.0:
                reasons.append(f"Excellent form ({candidate['form']:.1f})")
            elif candidate['form'] > 4.0:
                reasons.append(f"Good form ({candidate['form']:.1f})")

            options.append({
                'rank': i + 1,
                'player_id': candidate['player_id'],
                'name': candidate['name'],
                'team': candidate['team'],
                'position': candidate['position'],
                'expected_points': candidate['expected_points'],
                'risk_profile': candidate['risk_profile'],
                'risk_color': candidate['risk_color'],
                'ownership': candidate['ownership'],
                'reasons': reasons,
                'recommendation': self._get_captain_recommendation(i, candidate)
            })

        return options

    def _get_captain_recommendation(self, rank: int, candidate: Dict) -> str:
        """Generate recommendation text for captain option."""
        if rank == 0:
            # First option - safe/template recommendation
            if candidate['ownership'] > 50.0:
                return "Safest choice - template captain, minimal risk"
            elif candidate['risk_profile'] == "Safe":
                return "Best choice - high floor with good ceiling"
            else:
                return "Recommended - highest expected points"
        elif rank == 1:
            # Second option - alternative
            if candidate['risk_profile'] == "Differential":
                return "Differential option - higher risk, higher reward"
            else:
                return "Solid alternative if concerned about top pick"
        else:
            # Third option - punt/differential
            if candidate['ownership'] < 20.0:
                return "Differential punt - rank climbing potential"
            else:
                return "Contrarian choice - fade the template"

    def analyze_template_matching(
        self,
        squad_player_ids: List[int],
        ownership_threshold: float = 30.0
    ) -> Dict:
        """
        Analyze how squad matches the template (most owned players).

        Template = players owned by >30% of managers (configurable threshold)

        Returns analysis of:
        - Template match percentage
        - Template players in squad
        - Missing template players (you don't own)
        - Differential players (low ownership)

        Args:
            squad_player_ids: List of player IDs in squad
            ownership_threshold: Ownership % threshold for "template" (default 30%)

        Returns:
            Dict with template analysis
        """
        squad_players = [self.data.get_player_by_id(pid) for pid in squad_player_ids]

        # Get all available players and identify template
        all_players = self.data.get_available_players()

        # Sort by ownership
        all_players_sorted = sorted(
            all_players,
            key=lambda p: p.selected_by_percent,
            reverse=True
        )

        # Identify template players (high ownership)
        template_players = [
            p for p in all_players_sorted
            if p.selected_by_percent >= ownership_threshold
        ][:30]  # Top 30 most owned

        # Calculate template matching
        template_ids = {p.id for p in template_players}
        squad_ids = set(squad_player_ids)

        template_in_squad = template_ids & squad_ids
        template_missing = template_ids - squad_ids

        template_match_pct = len(template_in_squad) / len(template_ids) * 100 if template_ids else 0

        # Identify differentials in squad (low ownership)
        differentials = [
            p for p in squad_players
            if p.selected_by_percent < 10.0
        ]

        # Sort template players by ownership for display
        template_in_squad_players = [
            p for p in squad_players
            if p.id in template_in_squad
        ]
        template_in_squad_players.sort(key=lambda p: p.selected_by_percent, reverse=True)

        template_missing_players = [
            p for p in template_players
            if p.id in template_missing
        ]
        template_missing_players.sort(key=lambda p: p.selected_by_percent, reverse=True)

        differentials.sort(key=lambda p: p.selected_by_percent)

        # Calculate average ownership
        avg_ownership = sum(p.selected_by_percent for p in squad_players) / len(squad_players)

        return {
            'template_match_pct': template_match_pct,
            'template_count': len(template_in_squad),
            'template_total': len(template_ids),
            'avg_ownership': avg_ownership,
            'template_in_squad': [
                {
                    'name': p.name,
                    'team': self.data.get_team_by_id(p.team_id).short_name,
                    'position': p.position,
                    'ownership': p.selected_by_percent,
                    'price': p.price
                }
                for p in template_in_squad_players[:10]  # Show top 10
            ],
            'template_missing': [
                {
                    'name': p.name,
                    'team': self.data.get_team_by_id(p.team_id).short_name,
                    'position': p.position,
                    'ownership': p.selected_by_percent,
                    'price': p.price
                }
                for p in template_missing_players[:5]  # Show top 5 missing
            ],
            'differentials': [
                {
                    'name': p.name,
                    'team': self.data.get_team_by_id(p.team_id).short_name,
                    'position': p.position,
                    'ownership': p.selected_by_percent,
                    'price': p.price
                }
                for p in differentials[:5]  # Show top 5 differentials
            ]
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
