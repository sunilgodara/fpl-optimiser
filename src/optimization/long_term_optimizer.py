"""
Long-term multi-horizon optimizer for maximizing cumulative season points.

This module implements dynamic programming and rolling horizon planning to optimize
FPL decisions across the entire season, not just individual gameweeks.

Key Features:
- Rolling 10-week detailed horizon planning
- Transfer sequencing (plan optimal transfer paths)
- Global chip coordination (Wildcard, Free Hit, BB, TC timing)
- Risk-aware optimization (variance modeling)
"""
from typing import Dict, List, Optional, Tuple, Set
from dataclasses import dataclass
from copy import deepcopy
import itertools
from ..data.models import Player, GameweekData
from .squad_optimizer import SquadOptimizer
from .chip_strategy import ChipStrategyOptimizer


@dataclass
class SquadState:
    """
    Represents the state of a squad at a specific gameweek.
    Used for dynamic programming state space.
    """
    gameweek: int
    squad_ids: List[int]  # 15 player IDs
    bank: float
    free_transfers: int
    chips_available: List[str]

    def get_hash(self) -> str:
        """Hash for state caching (simplified)."""
        return f"{self.gameweek}_{','.join(map(str, sorted(self.squad_ids)))}_{self.bank:.1f}_{self.free_transfers}"


@dataclass
class TransferDecision:
    """Represents a single gameweek's transfer decisions."""
    gameweek: int
    transfers_out: List[int]  # Player IDs to transfer out
    transfers_in: List[int]   # Player IDs to transfer in
    hits_taken: int           # Number of -4 hits
    chip_used: Optional[str]  # 'wildcard', 'freehit', 'bboost', '3xc', or None
    expected_points: float
    squad_after: List[int]    # Squad after transfers
    bank_after: float
    free_transfers_after: int


@dataclass
class SeasonPlan:
    """Complete season strategy from current GW to GW38."""
    decisions: List[TransferDecision]  # Decision for each GW
    total_expected_points: float
    total_transfer_cost: int  # Total -4 hits taken
    net_expected_points: float  # After transfer costs
    chip_schedule: Dict[str, int]  # Chip -> GW mapping
    reasoning: str


class LongTermOptimizer:
    """
    Optimizes FPL decisions for the entire season using rolling horizon planning.

    Algorithm:
    1. Plan next 10 GWs in detail (full combinatorial search)
    2. Use aggregate value for GW+11 to GW38
    3. Re-plan each week as new info arrives (rolling horizon)

    This avoids myopic optimization (optimizing each GW independently).
    """

    def __init__(
        self,
        gameweek_data: GameweekData,
        current_squad: List[int],
        bank: float,
        free_transfers: int,
        chips_available: List[str]
    ):
        self.data = gameweek_data
        self.current_squad = current_squad
        self.bank = bank
        self.free_transfers = free_transfers
        self.chips_available = chips_available
        self.squad_optimizer = SquadOptimizer(gameweek_data)
        self.chip_optimizer = ChipStrategyOptimizer(gameweek_data)

        # Cache for optimization results
        self._state_cache: Dict[str, SeasonPlan] = {}

    def optimize_season(
        self,
        expected_points_by_week: Dict[int, Dict[int, float]],
        horizon: int = 10,
        strategy: str = 'cumulative_points',
        max_transfer_combinations: int = 100
    ) -> SeasonPlan:
        """
        Finds optimal sequence of decisions for remaining season.

        Args:
            expected_points_by_week: {gw: {player_id: ep}} for each future GW
            horizon: Number of GWs to plan in detail (default 10)
            strategy: 'cumulative_points', 'rank_climb', or 'rank_protect'
            max_transfer_combinations: Limit transfer paths to evaluate

        Returns:
            SeasonPlan with optimal decisions for each GW
        """
        current_gw = self.data.current_gameweek

        # Step 1: Globally optimize chip timing first
        chip_schedule = self._optimize_global_chip_timing(
            expected_points_by_week,
            horizon=horizon
        )

        # Step 2: Build optimal transfer path given chip schedule
        transfer_path = self._optimize_transfer_sequence(
            expected_points_by_week,
            chip_schedule,
            horizon=horizon,
            max_combinations=max_transfer_combinations
        )

        # Step 3: Package results
        total_ep = sum(d.expected_points for d in transfer_path)
        total_cost = sum(d.hits_taken * 4 for d in transfer_path)
        net_ep = total_ep - total_cost

        reasoning = self._generate_reasoning(transfer_path, chip_schedule, horizon)

        return SeasonPlan(
            decisions=transfer_path,
            total_expected_points=total_ep,
            total_transfer_cost=total_cost,
            net_expected_points=net_ep,
            chip_schedule=chip_schedule,
            reasoning=reasoning
        )

    def _optimize_global_chip_timing(
        self,
        expected_points_by_week: Dict[int, Dict[int, float]],
        horizon: int
    ) -> Dict[str, int]:
        """
        Finds globally optimal chip timing considering all chips together.

        This is crucial because chips interact:
        - Wildcard enables different squad structure
        - Free Hit allows temporary punts without disrupting long-term plan
        - Bench Boost value depends on squad composition from Wildcard
        - Triple Captain timing depends on fixture schedule

        Returns:
            Dict mapping chip name -> gameweek
        """
        current_gw = self.data.current_gameweek

        # Get chip evaluations from existing optimizer
        chip_evals = self.chip_optimizer.get_chip_strategy(
            self.current_squad,
            expected_points_by_week,
            self.chips_available,
            horizon=horizon,
            free_transfers=self.free_transfers
        )

        # Extract best GW for each chip (already conflict-resolved)
        chip_schedule = {}
        for chip_name, chip_data in chip_evals.items():
            if chip_name == '_conflicts' or chip_name.startswith('_'):
                continue

            # Additional check for Wildcard: Don't use if we have enough free transfers
            if 'wildcard' in chip_name:
                best_gw = chip_data.get('best_gameweek')
                evaluations = chip_data.get('evaluations', {})

                if best_gw and best_gw in evaluations:
                    transfers_needed = evaluations[best_gw].get('transfers_needed', 0)

                    print(f"\n🔍 DEBUG - Wildcard Check:")
                    print(f"   Transfers needed: {transfers_needed}")
                    print(f"   Free transfers: {self.free_transfers}")
                    print(f"   Should skip? {transfers_needed <= self.free_transfers}")

                    if transfers_needed <= self.free_transfers:
                        print(f"   ❌ SKIPPING Wildcard (you have enough FTs)")
                        continue

            if chip_data.get('recommended', False):
                chip_schedule[chip_name] = chip_data['best_gameweek']

        # Additional optimization: Check if moving chips creates better combos
        # For example, using Wildcard GW-1 before Bench Boost GW enables better BB value
        chip_schedule = self._refine_chip_sequence(chip_schedule, expected_points_by_week)

        return chip_schedule

    def _refine_chip_sequence(
        self,
        initial_schedule: Dict[str, int],
        expected_points_by_week: Dict[int, Dict[int, float]]
    ) -> Dict[str, int]:
        """
        Refines chip timing by checking if reordering improves total value.

        Key insight: Wildcard -> Bench Boost combo is powerful if WC is 1-2 GWs before BB.
        """
        if 'wildcard' not in initial_schedule or 'bench_boost' not in initial_schedule:
            return initial_schedule

        wc_gw = initial_schedule['wildcard']
        bb_gw = initial_schedule['bench_boost']

        # If BB is within 1-2 GWs after WC, keep it
        if 1 <= (bb_gw - wc_gw) <= 2:
            return initial_schedule

        # Otherwise, try moving BB closer to WC
        refined = initial_schedule.copy()

        # Check if WC+1 or WC+2 is available (no other chip scheduled)
        used_gws = set(initial_schedule.values())

        for offset in [1, 2]:
            candidate_gw = wc_gw + offset
            if candidate_gw not in used_gws:
                # Move BB to this GW
                refined['bench_boost'] = candidate_gw
                break

        return refined

    def _optimize_transfer_sequence(
        self,
        expected_points_by_week: Dict[int, Dict[int, float]],
        chip_schedule: Dict[str, int],
        horizon: int,
        max_combinations: int
    ) -> List[TransferDecision]:
        """
        Finds optimal sequence of transfers over the horizon.

        Uses beam search to evaluate transfer paths:
        1. For each GW, generate possible transfer options
        2. Evaluate each path's cumulative value
        3. Keep top K paths (beam width)
        4. Extend each path to next GW
        5. Return best complete path

        Args:
            expected_points_by_week: EP predictions
            chip_schedule: When to use each chip
            horizon: GWs to plan
            max_combinations: Beam width (paths to keep)

        Returns:
            List of TransferDecision for each GW
        """
        current_gw = self.data.current_gameweek
        # Start from next unplayed gameweek (current_gw is already finished)
        next_gw = current_gw + 1

        # Initialize beam with current state
        current_state = SquadState(
            gameweek=next_gw,  # Start from next unplayed GW, not current (finished) GW
            squad_ids=self.current_squad.copy(),
            bank=self.bank,
            free_transfers=self.free_transfers,
            chips_available=self.chips_available.copy()
        )

        # Build transfer path GW by GW
        best_path: List[TransferDecision] = []
        state = current_state

        # Start from next unplayed gameweek (current_gw is already finished)
        next_gw = current_gw + 1

        for gw in range(next_gw, next_gw + horizon):
            # Check if chip is scheduled for this GW
            chip_this_gw = None
            for chip_name, chip_gw in chip_schedule.items():
                if chip_gw == gw:
                    chip_this_gw = chip_name
                    break

            # Generate transfer decision for this GW
            decision = self._optimize_single_gw_with_context(
                state,
                expected_points_by_week.get(gw, {}),
                chip_this_gw,
                future_gws=list(range(gw + 1, next_gw + horizon)),
                expected_points_by_week=expected_points_by_week  # Pass full predictions for Wildcard
            )

            best_path.append(decision)

            # Update state for next GW
            state = SquadState(
                gameweek=gw + 1,
                squad_ids=decision.squad_after.copy(),
                bank=decision.bank_after,
                free_transfers=decision.free_transfers_after,
                chips_available=[c for c in state.chips_available if c != chip_this_gw]
            )

        return best_path

    def _optimize_single_gw_with_context(
        self,
        state: SquadState,
        ep_this_gw: Dict[int, float],
        chip_this_gw: Optional[str],
        future_gws: List[int],
        expected_points_by_week: Optional[Dict[int, Dict[int, float]]] = None
    ) -> TransferDecision:
        """
        Optimizes transfers for a single GW considering future context.

        Key insight: Don't just maximize THIS gameweek's points.
        Consider fixture swing duration, price changes, and future flexibility.

        Args:
            state: Current squad state
            ep_this_gw: Expected points for this GW
            chip_this_gw: Chip to use this GW (or None)
            future_gws: Upcoming GWs to consider
            expected_points_by_week: Full predictions by week (for Wildcard multi-week optimization)

        Returns:
            TransferDecision for this GW
        """
        gw = state.gameweek

        # Handle Wildcard: Unlimited transfers (optimize for 5-week horizon)
        if chip_this_gw and 'wildcard' in chip_this_gw:
            return self._handle_wildcard_gw(state, ep_this_gw, expected_points_by_week, gw)

        # Handle Free Hit: Temporary squad for 1 GW
        if chip_this_gw and ('freehit' in chip_this_gw or 'free_hit' in chip_this_gw):
            return self._handle_freehit_gw(state, ep_this_gw)

        # Regular transfers: Optimize with future context
        return self._handle_regular_transfers(state, ep_this_gw, future_gws, chip_this_gw)

    def _handle_wildcard_gw(
        self,
        state: SquadState,
        ep_this_gw: Dict[int, float],
        expected_points_by_week: Optional[Dict[int, Dict[int, float]]] = None,
        current_gw: int = None
    ) -> TransferDecision:
        """
        Build optimal 15-man squad from scratch using Wildcard.

        CRITICAL: Wildcard should optimize for medium-term (5 GWs), not just next GW.
        Otherwise we only make 2 transfers instead of rebuilding full squad.
        """
        print(f"\n🔍 _handle_wildcard_gw DEBUG:")
        print(f"   current_gw: {current_gw}")
        print(f"   expected_points_by_week is None: {expected_points_by_week is None}")
        if expected_points_by_week:
            print(f"   expected_points_by_week keys: {sorted(list(expected_points_by_week.keys()))}")
        print(f"   ep_this_gw players: {len(ep_this_gw)}")

        # Aggregate predictions over next 5 gameweeks for medium-term optimization
        WILDCARD_HORIZON = 5
        aggregated_ep = {}

        if expected_points_by_week and current_gw:
            print(f"\n🔍 Wildcard Optimization:")
            print(f"   Aggregating predictions over GW{current_gw} to GW{current_gw + WILDCARD_HORIZON - 1}")

            # Sum expected points for each player over the 5-week window
            for gw in range(current_gw, current_gw + WILDCARD_HORIZON):
                if gw in expected_points_by_week:
                    for player_id, ep in expected_points_by_week[gw].items():
                        aggregated_ep[player_id] = aggregated_ep.get(player_id, 0) + ep

            print(f"   Total players with predictions: {len(aggregated_ep)}")

            # Debug: Show top 10 players by aggregated EP
            if aggregated_ep:
                player_names = {p.id: p.name for p in self.data.players}

                top_players = sorted(aggregated_ep.items(), key=lambda x: x[1], reverse=True)[:10]
                print(f"\n   Top 10 players by 5-week aggregated EP:")
                for i, (pid, ep) in enumerate(top_players, 1):
                    name = player_names.get(pid, f"ID:{pid}")
                    print(f"      {i}. {name}: {ep:.1f} total pts")

                # Check specific elite players
                elite_names = ['Salah', 'Haaland', 'Palmer', 'Saka', 'Son', 'Alexander-Arnold', 'Isak']
                print(f"\n   Elite player predictions:")
                for elite_name in elite_names:
                    found = False
                    for pid, ep in aggregated_ep.items():
                        player_name = player_names.get(pid, "")
                        if elite_name.lower() in player_name.lower():
                            # Find in all players for full details
                            player = next((p for p in self.data.players if p.id == pid), None)
                            if player:
                                status_str = f" [{player.status}]" if player.status != 'a' else ""
                                print(f"      {player.name} (£{player.price}m){status_str}: {ep:.1f} pts (available: {player.is_available()})")
                                found = True
                                break
                    if not found:
                        print(f"      {elite_name}: NOT FOUND in predictions")

            # Use aggregated predictions for optimization
            optimize_ep = aggregated_ep if aggregated_ep else ep_this_gw
        else:
            # Fallback to single GW if multi-week data not available
            optimize_ep = ep_this_gw

        # Use squad optimizer to build best squad for 5-week horizon
        optimal = self.squad_optimizer.optimize_squad(optimize_ep, verbose=False)

        if not optimal:
            # Fallback: Keep current squad
            return TransferDecision(
                gameweek=state.gameweek,
                transfers_out=[],
                transfers_in=[],
                hits_taken=0,
                chip_used='wildcard',
                expected_points=sum(ep_this_gw.get(pid, 0) for pid in state.squad_ids) * 0.73,
                squad_after=state.squad_ids.copy(),
                bank_after=state.bank,
                free_transfers_after=1
            )

        # Calculate transfers needed
        current_set = set(state.squad_ids)
        new_set = set(optimal['squad'])
        transfers_out = list(current_set - new_set)
        transfers_in = list(new_set - current_set)

        print(f"   Transfers: {len(transfers_in)} in, {len(transfers_out)} out")
        print(f"   5-week total EP: {optimal['total_expected_points']:.1f}")
        print(f"   Squad cost: £{optimal['total_cost']:.1f}m")
        print(f"   Bank remaining: £{optimal['remaining_budget']:.1f}m")

        # Debug: Show selected squad
        if optimal.get('squad'):
            all_players = {p.id: p for p in self.data.players}

            selected_with_ep = [(pid, optimize_ep.get(pid, 0)) for pid in optimal['squad']]
            selected_with_ep.sort(key=lambda x: x[1], reverse=True)

            print(f"\n   Selected squad (top 11 by 5-week EP):")
            for i, (pid, ep) in enumerate(selected_with_ep[:11], 1):
                player = all_players.get(pid)
                if player:
                    print(f"      {i}. {player.name} (£{player.price}m): {ep:.1f} pts")

        # Calculate THIS gameweek's expected points (for display)
        this_gw_ep = sum(ep_this_gw.get(pid, 0) for pid in optimal['squad'])
        this_gw_best11 = sorted([ep_this_gw.get(pid, 0) for pid in optimal['squad']], reverse=True)[:11]
        this_gw_points = sum(this_gw_best11)

        print(f"   This GW (GW{current_gw}) EP: {this_gw_points:.1f}")

        return TransferDecision(
            gameweek=state.gameweek,
            transfers_out=transfers_out,
            transfers_in=transfers_in,
            hits_taken=0,  # Wildcard = no hits
            chip_used='wildcard',
            expected_points=this_gw_points,  # This GW's expected points for display
            squad_after=optimal['squad'],
            bank_after=optimal.get('remaining_budget', 0),
            free_transfers_after=1  # Reset to 1 FT after Wildcard
        )

    def _handle_freehit_gw(
        self,
        state: SquadState,
        ep_this_gw: Dict[int, float]
    ) -> TransferDecision:
        """Build optimal squad for this GW only, reverts next GW."""
        # Use squad optimizer for this GW
        optimal = self.squad_optimizer.optimize_squad(ep_this_gw, verbose=False)

        if not optimal:
            return TransferDecision(
                gameweek=state.gameweek,
                transfers_out=[],
                transfers_in=[],
                hits_taken=0,
                chip_used='freehit',
                expected_points=sum(ep_this_gw.get(pid, 0) for pid in state.squad_ids) * 0.73,
                squad_after=state.squad_ids.copy(),  # Reverts to original
                bank_after=state.bank,
                free_transfers_after=state.free_transfers
            )

        return TransferDecision(
            gameweek=state.gameweek,
            transfers_out=[],  # Temporary, doesn't affect real squad
            transfers_in=[],
            hits_taken=0,
            chip_used='freehit',
            expected_points=optimal['total_expected_points'],
            squad_after=state.squad_ids.copy(),  # Reverts to original squad
            bank_after=state.bank,  # Reverts to original bank
            free_transfers_after=state.free_transfers  # Reverts
        )

    def _handle_regular_transfers(
        self,
        state: SquadState,
        ep_this_gw: Dict[int, float],
        future_gws: List[int],
        chip_this_gw: Optional[str]
    ) -> TransferDecision:
        """
        Optimize regular transfers considering future value.

        For each possible transfer (or set of transfers):
        1. Calculate immediate EP gain (this GW)
        2. Calculate future EP gain (next 3-5 GWs)
        3. Consider price change value
        4. Consider squad flexibility for future moves
        5. Pick transfer(s) with highest total value
        """
        # Get available transfer budget
        num_free = state.free_transfers
        max_transfers = min(num_free + 3, 5)  # Can take up to 3 hits (or reach 5 total)

        # Generate candidate transfers
        candidates = self._generate_transfer_candidates(
            state,
            ep_this_gw,
            future_gws,
            max_transfers=max_transfers
        )

        # Evaluate each candidate
        best_candidate = None
        best_value = float('-inf')

        for candidate in candidates:
            # Calculate total value including future
            value = self._evaluate_transfer_value(
                candidate,
                state,
                ep_this_gw,
                future_gws
            )

            if value > best_value:
                best_value = value
                best_candidate = candidate

        # Return best decision
        if best_candidate:
            hits_taken = max(0, best_candidate['num_transfers'] - num_free)
            new_squad = state.squad_ids.copy()

            # Apply transfers
            for out_id in best_candidate['transfers_out']:
                new_squad.remove(out_id)
            for in_id in best_candidate['transfers_in']:
                new_squad.append(in_id)

            # Calculate new bank (simplified - doesn't account for exact prices)
            new_bank = state.bank - best_candidate.get('cost_delta', 0)

            # Calculate expected points for new squad
            squad_ep = self._calculate_squad_ep(new_squad, ep_this_gw)

            # Free transfers for next week
            if best_candidate['num_transfers'] == 0:
                next_ft = min(num_free + 1, 5)  # Bank unused transfer (max 5)
            else:
                next_ft = 1  # Reset to 1 after using transfers

            return TransferDecision(
                gameweek=state.gameweek,
                transfers_out=best_candidate['transfers_out'],
                transfers_in=best_candidate['transfers_in'],
                hits_taken=hits_taken,
                chip_used=chip_this_gw,
                expected_points=squad_ep,
                squad_after=new_squad,
                bank_after=new_bank,
                free_transfers_after=next_ft
            )

        # No good transfers found - roll transfer
        return TransferDecision(
            gameweek=state.gameweek,
            transfers_out=[],
            transfers_in=[],
            hits_taken=0,
            chip_used=chip_this_gw,
            expected_points=self._calculate_squad_ep(state.squad_ids, ep_this_gw),
            squad_after=state.squad_ids.copy(),
            bank_after=state.bank,
            free_transfers_after=min(num_free + 1, 5)
        )

    def _generate_transfer_candidates(
        self,
        state: SquadState,
        ep_this_gw: Dict[int, float],
        future_gws: List[int],
        max_transfers: int
    ) -> List[Dict]:
        """
        Generates promising transfer combinations to evaluate.

        Uses heuristics to prune search space:
        - Only consider transferring out underperforming players
        - Only consider transferring in high EP players
        - Limit to reasonable combinations (not all possible permutations)
        """
        candidates = []

        # Option 1: No transfers (roll FT)
        candidates.append({
            'transfers_out': [],
            'transfers_in': [],
            'num_transfers': 0,
            'cost_delta': 0
        })

        # Get weak players in current squad
        squad_players = [self.data.get_player_by_id(pid) for pid in state.squad_ids]
        weak_players = sorted(
            squad_players,
            key=lambda p: ep_this_gw.get(p.id, 0)
        )[:10]  # Bottom 10 players by EP

        # Get strong available players
        available = self.data.get_available_players()
        strong_players = sorted(
            [p for p in available if p.id not in state.squad_ids],
            key=lambda p: ep_this_gw.get(p.id, 0),
            reverse=True
        )[:20]  # Top 20 available players

        # Generate 1-transfer candidates
        for out_player in weak_players[:5]:  # Only bottom 5
            for in_player in strong_players[:10]:  # Only top 10 available
                # Check position compatibility
                if out_player.position == in_player.position:
                    # Simplified price check (would need proper calculation)
                    candidates.append({
                        'transfers_out': [out_player.id],
                        'transfers_in': [in_player.id],
                        'num_transfers': 1,
                        'cost_delta': in_player.price - out_player.price
                    })

        # Generate 2-transfer candidates (if we have 2+ FTs)
        if max_transfers >= 2:
            for out1, out2 in itertools.combinations(weak_players[:5], 2):
                for in1, in2 in itertools.combinations(strong_players[:10], 2):
                    # Check positions match
                    if (out1.position == in1.position and out2.position == in2.position) or \
                       (out1.position == in2.position and out2.position == in1.position):
                        candidates.append({
                            'transfers_out': [out1.id, out2.id],
                            'transfers_in': [in1.id, in2.id],
                            'num_transfers': 2,
                            'cost_delta': (in1.price + in2.price) - (out1.price + out2.price)
                        })

        return candidates[:100]  # Limit to 100 candidates max

    def _evaluate_transfer_value(
        self,
        candidate: Dict,
        state: SquadState,
        ep_this_gw: Dict[int, float],
        future_gws: List[int]
    ) -> float:
        """
        Evaluates total value of a transfer considering:
        1. Immediate EP gain (this GW)
        2. Future EP gain (next 3-5 GWs)
        3. Transfer cost (-4 per hit)
        4. Price change value (simplified)
        """
        if candidate['num_transfers'] == 0:
            return 0  # No value from rolling

        # Calculate EP gain
        out_ids = candidate['transfers_out']
        in_ids = candidate['transfers_in']

        immediate_gain = sum(ep_this_gw.get(pid, 0) for pid in in_ids) - \
                        sum(ep_this_gw.get(pid, 0) for pid in out_ids)

        # Future value (simplified - next 3 GWs)
        future_gain = 0
        # TODO: Implement proper future EP calculation using expected_points_by_week

        # Transfer cost
        num_free = state.free_transfers
        hits = max(0, candidate['num_transfers'] - num_free)
        transfer_cost = hits * 4

        # Total value
        total_value = immediate_gain + future_gain - transfer_cost

        return total_value

    def _calculate_squad_ep(
        self,
        squad_ids: List[int],
        ep_dict: Dict[int, float]
    ) -> float:
        """Calculate expected points for squad (best 11 of 15)."""
        squad_eps = sorted([ep_dict.get(pid, 0) for pid in squad_ids], reverse=True)
        return sum(squad_eps[:11])  # Top 11 players

    def _generate_reasoning(
        self,
        decisions: List[TransferDecision],
        chip_schedule: Dict[str, int],
        horizon: int
    ) -> str:
        """Generate human-readable explanation of the season plan."""
        lines = []
        lines.append(f"🎯 LONG-TERM SEASON PLAN ({horizon}-Week Horizon)")
        lines.append("")

        # Chip strategy summary
        if chip_schedule:
            lines.append("📅 CHIP SCHEDULE:")
            for chip, gw in sorted(chip_schedule.items(), key=lambda x: x[1]):
                chip_display = {
                    'wildcard': '🃏 Wildcard',
                    'freehit': '⚡ Free Hit',
                    'bench_boost': '💪 Bench Boost',
                    '3xc': '👑 Triple Captain'
                }.get(chip, chip)
                lines.append(f"  GW{gw}: {chip_display}")
            lines.append("")

        # Transfer strategy summary
        total_hits = sum(d.hits_taken for d in decisions)
        total_ep = sum(d.expected_points for d in decisions)
        net_ep = total_ep - (total_hits * 4)

        lines.append(f"📊 TRANSFER STRATEGY:")
        lines.append(f"  Total Expected Points: {total_ep:.1f}")
        lines.append(f"  Total Transfer Hits: {total_hits} (-{total_hits * 4} points)")
        lines.append(f"  Net Expected Points: {net_ep:.1f}")
        lines.append("")

        lines.append("🔄 GAMEWEEK BREAKDOWN:")
        for decision in decisions[:5]:  # Show first 5 GWs
            gw_line = f"  GW{decision.gameweek}: "
            if decision.chip_used:
                gw_line += f"Use {decision.chip_used.upper()}, "
            if decision.transfers_in:
                gw_line += f"{len(decision.transfers_in)} transfer(s), "
            if decision.hits_taken > 0:
                gw_line += f"-{decision.hits_taken * 4} pts hit, "
            gw_line += f"{decision.expected_points:.1f} EP"
            lines.append(gw_line)

        if len(decisions) > 5:
            lines.append(f"  ... (+ {len(decisions) - 5} more gameweeks)")

        return "\n".join(lines)
