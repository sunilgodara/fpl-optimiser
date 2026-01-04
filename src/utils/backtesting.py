"""
Backtesting framework to evaluate optimizer strategies on historical data.
"""
from typing import Dict, List, Optional, Callable
from dataclasses import dataclass
from ..data.models import Player, GameweekData
from ..optimization.squad_optimizer import SquadOptimizer
from ..optimization.transfer_optimizer import TransferOptimizer


@dataclass
class GameweekResult:
    """Results for a single gameweek."""
    gameweek: int
    squad: List[int]
    starting_xi: List[int]
    captain: int
    vice_captain: Optional[int]
    bench: List[int]
    transfers_made: List[Dict]
    chip_used: Optional[str]
    predicted_points: float
    actual_points: float
    transfer_cost: int
    net_points: float  # actual_points - transfer_cost
    squad_value: float
    bank: float


@dataclass
class BacktestResult:
    """Results from a full backtest."""
    total_points: float
    gameweek_results: List[GameweekResult]
    final_squad_value: float
    final_bank: float
    total_transfers: int
    total_transfer_cost: int
    chips_used: Dict[str, int]  # chip_name -> gameweek used
    rank_estimate: Optional[int]


class Backtester:
    """
    Backtest FPL strategies on historical data.

    Note: This is a simplified backtester. For real historical testing,
    you'd need to fetch actual historical data from FPL API or database.
    """

    INITIAL_BUDGET = 100.0
    FREE_TRANSFERS_PER_WEEK = 1

    def __init__(self):
        self.results: List[GameweekResult] = []

    def simulate_gameweek(
        self,
        gameweek: int,
        current_squad: List[int],
        predicted_points: Dict[int, float],
        actual_points: Dict[int, float],
        data: GameweekData,
        transfers: Optional[List[Dict]] = None,
        chip: Optional[str] = None,
        bank: float = 0.0
    ) -> GameweekResult:
        """
        Simulate a single gameweek.

        Args:
            gameweek: Gameweek number
            current_squad: Current squad player IDs
            predicted_points: Predicted points for this gameweek
            actual_points: Actual points scored (from historical data)
            data: GameweekData
            transfers: List of transfers made this week
            chip: Chip used this week
            bank: Money in bank

        Returns:
            GameweekResult
        """
        # Apply transfers if any
        working_squad = current_squad.copy()
        transfer_cost = 0

        if transfers:
            for transfer in transfers:
                working_squad.remove(transfer['player_out_id'])
                working_squad.append(transfer['player_in_id'])
                if 'cost' in transfer:
                    transfer_cost += transfer['cost']

        # Optimize starting XI for this gameweek
        optimizer = SquadOptimizer(data)
        starting_result = optimizer.optimize_starting_xi(
            working_squad,
            predicted_points,
            verbose=False
        )

        if not starting_result:
            # Fallback: just take top 11 by predicted points
            sorted_squad = sorted(
                working_squad,
                key=lambda pid: predicted_points.get(pid, 0),
                reverse=True
            )
            starting_xi = sorted_squad[:11]
            captain = starting_xi[0]
            bench = sorted_squad[11:]
        else:
            starting_xi = starting_result['starting_xi']
            captain = starting_result['captain']
            bench = [pid for pid in working_squad if pid not in starting_xi]

        # Calculate actual points scored
        points_scored = 0

        # Starting XI points
        for pid in starting_xi:
            player_points = actual_points.get(pid, 0)
            points_scored += player_points

        # Captain bonus (2x for normal, 3x for triple captain)
        captain_points = actual_points.get(captain, 0)
        if chip == '3xc':
            points_scored += captain_points * 2  # Extra 2x (already counted 1x)
        else:
            points_scored += captain_points  # Extra 1x

        # Bench boost: add bench points
        if chip == 'bboost':
            for pid in bench:
                points_scored += actual_points.get(pid, 0)

        # Apply transfer cost
        net_points = points_scored - transfer_cost

        # Calculate squad value
        squad_value = sum(
            data.get_player_by_id(pid).price for pid in working_squad
        )

        return GameweekResult(
            gameweek=gameweek,
            squad=working_squad,
            starting_xi=starting_xi,
            captain=captain,
            vice_captain=None,
            bench=bench,
            transfers_made=transfers or [],
            chip_used=chip,
            predicted_points=sum(predicted_points.get(pid, 0) for pid in starting_xi),
            actual_points=points_scored,
            transfer_cost=transfer_cost,
            net_points=net_points,
            squad_value=squad_value,
            bank=bank
        )

    def run_backtest(
        self,
        start_gameweek: int,
        end_gameweek: int,
        initial_squad: List[int],
        prediction_function: Callable,
        transfer_strategy: str = 'conservative',
        chip_strategy: Optional[Dict] = None,
        data: GameweekData = None
    ) -> BacktestResult:
        """
        Run full backtest over a season.

        Args:
            start_gameweek: Starting gameweek
            end_gameweek: Ending gameweek
            initial_squad: Initial 15-player squad
            prediction_function: Function that returns predicted points for a gameweek
            transfer_strategy: 'conservative', 'aggressive', or 'optimal'
            chip_strategy: Dict specifying when to use chips
            data: GameweekData

        Returns:
            BacktestResult
        """
        current_squad = initial_squad.copy()
        bank = 0.0
        free_transfers = 1
        total_points = 0
        total_transfers = 0
        total_transfer_cost = 0
        chips_used = {}

        gameweek_results = []

        for gw in range(start_gameweek, end_gameweek + 1):
            # Get predictions for this gameweek
            predicted_points = prediction_function(gw)

            # Determine transfers (simplified logic)
            transfers = []
            chip = None

            # Check if chip should be used
            if chip_strategy and gw in chip_strategy:
                chip = chip_strategy[gw]
                chips_used[chip] = gw

            # Transfer logic (simplified)
            if transfer_strategy == 'conservative':
                # Only transfer if free transfers available
                if free_transfers > 0:
                    # Make 1 transfer (would need actual transfer optimizer here)
                    pass

            # Simulate gameweek (would need actual points here)
            # For now, use predicted as actual (placeholder)
            actual_points = predicted_points  # In real backtest, fetch actual historical points

            gw_result = self.simulate_gameweek(
                gw, current_squad, predicted_points, actual_points,
                data, transfers, chip, bank
            )

            gameweek_results.append(gw_result)
            current_squad = gw_result.squad
            total_points += gw_result.net_points
            total_transfers += len(transfers)
            total_transfer_cost += gw_result.transfer_cost

            # Update free transfers
            if len(transfers) == 0:
                free_transfers = min(free_transfers + 1, 2)
            else:
                free_transfers = max(0, free_transfers - len(transfers))
                if free_transfers < 0:
                    free_transfers = 1  # Reset next week

        final_squad_value = gameweek_results[-1].squad_value if gameweek_results else 100.0

        return BacktestResult(
            total_points=total_points,
            gameweek_results=gameweek_results,
            final_squad_value=final_squad_value,
            final_bank=bank,
            total_transfers=total_transfers,
            total_transfer_cost=total_transfer_cost,
            chips_used=chips_used,
            rank_estimate=None
        )

    def compare_strategies(
        self,
        strategies: Dict[str, Dict],
        start_gameweek: int,
        end_gameweek: int,
        data: GameweekData
    ) -> Dict[str, BacktestResult]:
        """
        Compare multiple strategies.

        Args:
            strategies: Dict mapping strategy_name -> strategy_config
            start_gameweek: Start GW
            end_gameweek: End GW
            data: GameweekData

        Returns:
            Dict mapping strategy_name -> BacktestResult
        """
        results = {}

        for strategy_name, strategy_config in strategies.items():
            print(f"Running backtest for strategy: {strategy_name}")

            result = self.run_backtest(
                start_gameweek=start_gameweek,
                end_gameweek=end_gameweek,
                initial_squad=strategy_config['initial_squad'],
                prediction_function=strategy_config['prediction_function'],
                transfer_strategy=strategy_config.get('transfer_strategy', 'conservative'),
                chip_strategy=strategy_config.get('chip_strategy'),
                data=data
            )

            results[strategy_name] = result

        return results

    def print_backtest_summary(self, result: BacktestResult, strategy_name: str = ""):
        """Print summary of backtest results."""
        print("\n" + "=" * 80)
        if strategy_name:
            print(f"BACKTEST RESULTS: {strategy_name}")
        else:
            print("BACKTEST RESULTS")
        print("=" * 80)

        print(f"\nTotal Points: {result.total_points:.0f}")
        print(f"Total Transfers: {result.total_transfers}")
        print(f"Transfer Cost: -{result.total_transfer_cost} points")
        print(f"Final Squad Value: £{result.final_squad_value:.1f}m")
        print(f"Bank: £{result.final_bank:.1f}m")

        if result.chips_used:
            print("\nChips Used:")
            for chip, gw in result.chips_used.items():
                print(f"  - {chip}: GW{gw}")

        # Points distribution
        if result.gameweek_results:
            points_per_gw = [gw.net_points for gw in result.gameweek_results]
            avg_points = sum(points_per_gw) / len(points_per_gw)
            max_points = max(points_per_gw)
            min_points = min(points_per_gw)

            print(f"\nPoints per Gameweek:")
            print(f"  Average: {avg_points:.1f}")
            print(f"  Best: {max_points:.1f}")
            print(f"  Worst: {min_points:.1f}")

        print("=" * 80)

    def analyze_prediction_accuracy(
        self,
        gameweek_results: List[GameweekResult]
    ) -> Dict:
        """
        Analyze how accurate predictions were.

        Returns metrics on prediction vs actual performance.
        """
        total_predicted = 0
        total_actual = 0
        errors = []

        for gw_result in gameweek_results:
            total_predicted += gw_result.predicted_points
            total_actual += gw_result.actual_points
            error = abs(gw_result.predicted_points - gw_result.actual_points)
            errors.append(error)

        mae = sum(errors) / len(errors) if errors else 0  # Mean Absolute Error
        accuracy = (1 - mae / (total_actual / len(gameweek_results))) * 100 if total_actual > 0 else 0

        return {
            'total_predicted': total_predicted,
            'total_actual': total_actual,
            'mean_absolute_error': mae,
            'accuracy_percent': accuracy,
            'prediction_bias': total_predicted - total_actual,  # Positive = over-predicting
        }
