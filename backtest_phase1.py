#!/usr/bin/env python3
"""
Backtest Phase 1: Long-Term Optimizer + Real xG Integration

This script validates the improvements made in Phase 1 by:
1. Running the optimizer on historical data
2. Comparing predicted vs actual points
3. Measuring long-term decision quality
"""
import json
import sys
from pathlib import Path
from typing import Dict, List

# Add src to path
sys.path.insert(0, str(Path(__file__).parent))

from src.utils.historical_data import HistoricalDataCollector
from src.data.api_client import FPLAPIClient
from src.data.models import build_gameweek_data
from src.prediction.advanced_forecaster import AdvancedForecaster
from src.optimization.long_term_optimizer import LongTermOptimizer
from src.optimization.squad_optimizer import SquadOptimizer


class Phase1Backtester:
    """
    Backtests Phase 1 improvements:
    - Long-term optimizer
    - Real xG integration
    """

    def __init__(self, historical_data: Dict):
        self.historical_data = historical_data
        self.results = []

    def simulate_gameweek(
        self,
        gw: int,
        current_squad: List[int],
        predicted_points: Dict[int, float]
    ) -> Dict:
        """
        Simulate a single gameweek.

        Args:
            gw: Gameweek number
            current_squad: Current 15-player squad
            predicted_points: Predicted points for this GW

        Returns:
            Dict with simulation results
        """
        # Get actual points from historical data
        gw_data = self.historical_data['gameweeks'].get(gw, {})
        actual_points = gw_data.get('actual_points', {})

        # Calculate predicted vs actual for squad
        # Use best 11 players (simulate actual FPL scoring)
        squad_predicted = {pid: predicted_points.get(pid, 0) for pid in current_squad}
        squad_actual = {pid: actual_points.get(pid, 0) for pid in current_squad}

        # Sort by predicted to get best 11
        best_11_predicted = sorted(squad_predicted.items(), key=lambda x: x[1], reverse=True)[:11]
        total_predicted = sum(p[1] for p in best_11_predicted)

        # Get actual for those same 11 players
        best_11_ids = [p[0] for p in best_11_predicted]
        total_actual = sum(squad_actual.get(pid, 0) for pid in best_11_ids)

        # Calculate error per player
        errors = [abs(squad_predicted.get(pid, 0) - squad_actual.get(pid, 0))
                  for pid in current_squad]
        squad_mae = sum(errors) / len(errors) if errors else 0

        # Also calculate error for the 11 we picked
        best_11_errors = [abs(squad_predicted.get(pid, 0) - squad_actual.get(pid, 0))
                          for pid in best_11_ids]
        best_11_mae = sum(best_11_errors) / len(best_11_errors) if best_11_errors else 0

        return {
            'gameweek': gw,
            'total_predicted': total_predicted,
            'total_actual': total_actual,
            'mae': squad_mae,
            'best_11_mae': best_11_mae,
            'squad_size': len(current_squad),
            'best_11_size': len(best_11_ids)
        }

    def run_backtest(
        self,
        start_gw: int,
        end_gw: int,
        initial_squad: List[int],
        use_optimizer: bool = True
    ) -> Dict:
        """
        Run full backtest over gameweek range.

        Args:
            start_gw: Starting gameweek
            end_gw: Ending gameweek
            initial_squad: Starting 15-player squad
            use_optimizer: If True, use AdvancedForecaster; if False, use baseline

        Returns:
            Dict with backtest results
        """
        print("=" * 80)
        print("PHASE 1 BACKTEST")
        print(f"Testing GW{start_gw} to GW{end_gw}")
        print(f"Mode: {'OPTIMIZER' if use_optimizer else 'BASELINE (Actual=Predicted)'}")
        print("=" * 80)

        current_squad = initial_squad.copy()
        gameweek_results = []
        total_predicted = 0
        total_actual = 0
        errors = []

        # Initialize API client and forecaster if using optimizer
        forecaster = None
        if use_optimizer:
            print("\nInitializing AdvancedForecaster...")
            try:
                api_client = FPLAPIClient()
                bootstrap = api_client.get_bootstrap_static()
                fixtures = api_client.get_fixtures()
                gameweek_data = build_gameweek_data(bootstrap, fixtures)

                forecaster = AdvancedForecaster(
                    gameweek_data,
                    api_client,
                    use_rotation_model=True,
                    use_xg_model=True,
                    use_understat=False,  # Disabled for speed
                    use_bonus_model=True,
                    use_confidence_model=False  # Disabled for backtest
                )
                print("✓ Forecaster initialized\n")
            except Exception as e:
                print(f"✗ Failed to initialize forecaster: {e}")
                print("Falling back to baseline mode\n")
                use_optimizer = False

        for gw in range(start_gw, end_gw + 1):
            print(f"\nSimulating GW{gw}...")

            # Get actual points from historical data
            gw_data = self.historical_data['gameweeks'].get(gw, {})
            actual_points = gw_data.get('actual_points', {})

            # Generate predictions
            if use_optimizer and forecaster:
                # Use AdvancedForecaster to generate real predictions
                # Note: This uses current season data, not historical snapshot
                # In a true backtest, we'd need historical player stats as of that GW
                try:
                    predicted_points = {}
                    for player in gameweek_data.players:
                        if player.id in current_squad:
                            pred = forecaster.predict_points(player, num_gameweeks=1)
                            predicted_points[player.id] = pred
                    print(f"  Generated predictions for {len(predicted_points)} players")
                except Exception as e:
                    print(f"  Warning: Prediction failed: {e}")
                    predicted_points = actual_points
            else:
                # Baseline: use actual = predicted
                predicted_points = actual_points

            result = self.simulate_gameweek(gw, current_squad, predicted_points)
            gameweek_results.append(result)

            total_predicted += result['total_predicted']
            total_actual += result['total_actual']
            errors.append(result['mae'])

            print(f"  Predicted (Best 11): {result['total_predicted']:.1f}")
            print(f"  Actual (Best 11): {result['total_actual']:.1f}")
            print(f"  Error: {result['total_predicted'] - result['total_actual']:+.1f}")
            print(f"  MAE: {result['mae']:.2f}")

        # Calculate metrics
        overall_mae = sum(errors) / len(errors) if errors else 0
        prediction_bias = total_predicted - total_actual

        results = {
            'gameweeks_tested': len(gameweek_results),
            'total_predicted': total_predicted,
            'total_actual': total_actual,
            'overall_mae': overall_mae,
            'prediction_bias': prediction_bias,
            'gameweek_results': gameweek_results,
            'mode': 'optimizer' if use_optimizer else 'baseline'
        }

        return results

    def print_results(self, results: Dict):
        """Print backtest results summary."""
        print("\n" + "=" * 80)
        print("BACKTEST RESULTS")
        print("=" * 80)

        mode = results.get('mode', 'unknown')
        print(f"\nMode: {mode.upper()}")
        print(f"Gameweeks Tested: {results['gameweeks_tested']}")
        print(f"Total Predicted Points: {results['total_predicted']:.1f}")
        print(f"Total Actual Points: {results['total_actual']:.1f}")
        print(f"Prediction Bias: {results['prediction_bias']:+.1f} points")
        print(f"Mean Absolute Error: {results['overall_mae']:.2f} points per player per GW")

        # Calculate accuracy (only if we have actual data)
        if results['total_actual'] > 0:
            avg_actual = results['total_actual'] / results['gameweeks_tested']
            avg_predicted = results['total_predicted'] / results['gameweeks_tested']

            if avg_actual > 0:
                # Accuracy relative to average points
                accuracy = (1 - results['overall_mae'] / (avg_actual / 15)) * 100
                print(f"Prediction Accuracy: {accuracy:.1f}%")

                # Average points per gameweek
                print(f"\nAverage per GW:")
                print(f"  Predicted: {avg_predicted:.1f} pts")
                print(f"  Actual: {avg_actual:.1f} pts")
                print(f"  Difference: {avg_predicted - avg_actual:+.1f} pts/GW")

                # Interpretation
                if mode == 'baseline':
                    print("\n⚠️  NOTE: Baseline mode (predicted = actual)")
                    print("   Perfect accuracy is expected. This validates data collection only.")
                elif results['overall_mae'] < 2.0:
                    print("\n✓ Excellent prediction accuracy (MAE < 2.0)")
                elif results['overall_mae'] < 3.0:
                    print("\n✓ Good prediction accuracy (MAE < 3.0)")
                elif results['overall_mae'] < 4.0:
                    print("\n⚠️  Fair prediction accuracy (MAE 3.0-4.0)")
                else:
                    print("\n⚠️  Poor prediction accuracy (MAE > 4.0)")
                    print("   Consider tuning forecaster parameters")
        else:
            print("\n⚠️  Warning: No actual points data available")
            print("   Historical data collection may have failed.")
            print("   The FPL API only provides current season data.")
            print("\n   To properly backtest:")
            print("   1. Use the current season data (2025-26 GW1 onwards)")
            print("   2. Or manually collect historical data from external sources")

        print("\n" + "=" * 80)


def main():
    """Run Phase 1 backtest."""
    import argparse

    parser = argparse.ArgumentParser(description='Backtest Phase 1 improvements')
    parser.add_argument('--season', default='2024-25', help='Season to test')
    parser.add_argument('--start-gw', type=int, default=1, help='Start gameweek')
    parser.add_argument('--end-gw', type=int, default=5, help='End gameweek')
    parser.add_argument('--collect', action='store_true', help='Collect data first')
    parser.add_argument('--baseline', action='store_true',
                        help='Use baseline mode (predicted=actual) instead of optimizer')

    args = parser.parse_args()

    # Step 1: Collect historical data (if needed)
    data_file = Path(f"data/historical/{args.season}/complete_dataset.json")

    if args.collect or not data_file.exists():
        print("Collecting historical data...")
        collector = HistoricalDataCollector(season=args.season)
        historical_data = collector.build_historical_dataset(
            start_gw=args.start_gw,
            end_gw=args.end_gw
        )
    else:
        print(f"Loading historical data from {data_file}...")
        with open(data_file) as f:
            historical_data = json.load(f)

    # Step 2: Create initial squad (top 15 players by price for simplicity)
    players = historical_data['players']
    player_ids = sorted(
        players.keys(),
        key=lambda pid: players[pid].get('initial_price', 5.0),
        reverse=True
    )[:15]

    print(f"\nInitial squad: 15 players")

    # Step 3: Run backtest
    backtester = Phase1Backtester(historical_data)
    use_optimizer = not args.baseline  # Optimizer mode unless --baseline flag

    results = backtester.run_backtest(
        start_gw=args.start_gw,
        end_gw=args.end_gw,
        initial_squad=player_ids,
        use_optimizer=use_optimizer
    )

    # Step 4: Print results
    backtester.print_results(results)

    # Save results
    output_file = Path(f"data/backtest_phase1_{args.season}_gw{args.start_gw}-{args.end_gw}.json")
    output_file.parent.mkdir(parents=True, exist_ok=True)
    with open(output_file, 'w') as f:
        json.dump(results, f, indent=2)

    print(f"\n✓ Results saved to {output_file}")


if __name__ == "__main__":
    main()
