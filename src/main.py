"""
Main entry point for FPL Optimizer with advanced features.
"""
import argparse
from .data.api_client import FPLAPIClient
from .data.models import build_gameweek_data
from .prediction.forecaster import PointForecaster
from .prediction.advanced_forecaster import AdvancedForecaster
from .optimization.squad_optimizer import SquadOptimizer
from .optimization.transfer_optimizer import TransferOptimizer
from .optimization.chip_strategy import ChipStrategyOptimizer
from .utils.config import get_config, UserTeamConfig


def run_basic_optimizer(config):
    """Run basic optimization (original functionality)."""
    print("=" * 80)
    print("FPL OPTIMIZER - Basic Squad Optimization")
    print("=" * 80)

    # Fetch data
    print("\n[1/5] Fetching data from FPL API...")
    api_client = FPLAPIClient()
    gameweek_data = build_gameweek_data(api_client)

    print(f"  - Loaded {len(gameweek_data.players)} players")
    print(f"  - Loaded {len(gameweek_data.teams)} teams")
    print(f"  - Loaded {len(gameweek_data.fixtures)} upcoming fixtures")
    print(f"  - Current gameweek: {gameweek_data.current_gameweek}")

    # Predict points
    print(f"\n[2/5] Predicting player points (next {config.prediction_horizon} GWs)...")

    if config.use_advanced_predictions:
        forecaster = AdvancedForecaster(gameweek_data, api_client)
        print("  - Using advanced prediction engine with historical data")
    else:
        forecaster = PointForecaster(gameweek_data)
        print("  - Using basic prediction engine")

    expected_points = forecaster.get_predictions_for_all_players(
        num_gameweeks=config.prediction_horizon
    )

    # Show top predictions
    print("\n  Top 3 predicted players by position:")
    for position in ['GK', 'DEF', 'MID', 'FWD']:
        position_players = [
            p for p in gameweek_data.players
            if p.position == position and p.is_available()
        ]
        position_players.sort(
            key=lambda p: expected_points.get(p.id, 0),
            reverse=True
        )

        print(f"\n  {position}:")
        for player in position_players[:3]:
            team = gameweek_data.get_team_by_id(player.team_id)
            ep = expected_points.get(player.id, 0)
            print(f"    {player.name:20} ({team.short_name}) - "
                  f"£{player.price}m - EP: {ep:.2f}")

    # Optimize squad
    print("\n[3/5] Optimizing squad selection...")
    optimizer = SquadOptimizer(gameweek_data)
    squad_result = optimizer.optimize_squad(expected_points, verbose=False)

    if not squad_result:
        print("ERROR: Squad optimization failed!")
        return None

    print(f"  - Total expected points: {squad_result['total_expected_points']:.2f}")
    print(f"  - Total cost: £{squad_result['total_cost']:.1f}m")

    # Optimize starting XI
    print("\n[4/5] Optimizing starting XI and captain...")
    starting_result = optimizer.optimize_starting_xi(
        squad_result['squad'],
        expected_points,
        verbose=False
    )

    if not starting_result:
        print("ERROR: Starting XI optimization failed!")
        return None

    captain = gameweek_data.get_player_by_id(starting_result['captain'])
    print(f"  - Captain: {captain.name}")
    print(f"  - Total expected points: {starting_result['total_expected_points']:.2f}")

    # Display results
    print("\n[5/5] Final Squad:")
    optimizer.display_squad(
        squad_result['squad'],
        expected_points,
        starting_xi=starting_result['starting_xi'],
        captain_id=starting_result['captain']
    )

    bench = [pid for pid in squad_result['squad'] if pid not in starting_result['starting_xi']]
    print("\nBENCH:")
    print("-" * 80)
    for pid in bench:
        player = gameweek_data.get_player_by_id(pid)
        team = gameweek_data.get_team_by_id(player.team_id)
        ep = expected_points.get(pid, 0)
        print(f"  {player.name:20} ({player.position}) | {team.short_name:4} | "
              f"£{player.price:4.1f}m | EP: {ep:5.2f}")

    print("\n" + "=" * 80)

    return {
        'squad': squad_result['squad'],
        'starting_xi': starting_result['starting_xi'],
        'captain': starting_result['captain'],
        'expected_points': expected_points,
        'data': gameweek_data,
        'api_client': api_client,
    }


def run_advanced_optimizer(config, user_team_config):
    """Run advanced optimization with transfers and chip strategy."""
    print("=" * 80)
    print("FPL OPTIMIZER - Advanced Strategy Planning")
    print("=" * 80)

    # Fetch data
    print("\n[1/6] Fetching data from FPL API...")
    api_client = FPLAPIClient()
    gameweek_data = build_gameweek_data(api_client)

    print(f"  - Loaded {len(gameweek_data.players)} players")
    print(f"  - Current gameweek: {gameweek_data.current_gameweek}")

    # Fetch user's team if team_id provided
    if user_team_config.team_id:
        print(f"\n[2/6] Fetching your FPL team (ID: {user_team_config.team_id})...")
        team_data = api_client.get_team_current_squad(user_team_config.team_id)
        if team_data:
            user_team_config.current_squad = team_data['squad']

            # Use fetched data unless overridden
            if args.bank is None:
                user_team_config.bank = team_data['bank']
            if args.free_transfers is None:
                user_team_config.free_transfers = team_data.get('free_transfers', 1)

            print(f"  - Team: {team_data['team_name']}")
            print(f"  - Manager: {team_data['player_name']}")
            print(f"  - Overall Rank: {team_data['overall_rank']:,}")
            print(f"  - Total Points: {team_data['total_points']}")
            print(f"  - Squad Value: £{team_data['squad_value']:.1f}m")
            print(f"  - Bank: £{user_team_config.bank:.1f}m{' (manual override)' if args.bank is not None else ''}")
            print(f"  - Free Transfers: {user_team_config.free_transfers}{' (manual override)' if args.free_transfers is not None else ' (API estimate - may be inaccurate)'}")

            if args.free_transfers is None and team_data.get('transfers_made_this_week', 0) == 0:
                print(f"  - Note: No transfers made in GW{gameweek_data.current_gameweek}. You likely have 2+ free transfers.")
                print(f"           Use --free-transfers to specify exact count (e.g., --free-transfers 5)")
        else:
            print(f"  - Could not fetch team data. Will optimize new squad.")

    # Advanced predictions
    print(f"\n[{'3' if user_team_config.team_id else '2'}/6] Generating advanced predictions...")
    forecaster = AdvancedForecaster(gameweek_data, api_client)

    # Generate predictions for multiple gameweeks
    expected_points_by_week = {}
    for gw_offset in range(config.chip_planning_horizon):
        gw = gameweek_data.current_gameweek + gw_offset
        ep = forecaster.get_predictions_for_all_players(num_gameweeks=1)
        expected_points_by_week[gw] = ep

    # Current predictions (next 3 weeks)
    expected_points = forecaster.get_predictions_for_all_players(
        num_gameweeks=config.prediction_horizon
    )

    print(f"  - Generated {config.chip_planning_horizon}-week forecast")

    # Get or optimize squad
    step_num = 4 if user_team_config.team_id else 3
    if user_team_config.current_squad:
        print(f"\n[{step_num}/6] Using your current squad ({len(user_team_config.current_squad)} players)...")
        current_squad = user_team_config.current_squad
    else:
        print(f"\n[{step_num}/6] No current squad provided - optimizing new squad...")
        optimizer = SquadOptimizer(gameweek_data)
        squad_result = optimizer.optimize_squad(expected_points, verbose=False)
        if not squad_result:
            print("ERROR: Squad optimization failed!")
            return None
        current_squad = squad_result['squad']
        print(f"  - Optimized squad: {squad_result['total_expected_points']:.2f} EP")

    # Transfer planning
    step_num = 5 if user_team_config.team_id else 4
    print(f"\n[{step_num}/6] Planning transfers (next {config.transfer_planning_horizon} weeks)...")
    transfer_optimizer = TransferOptimizer(gameweek_data)

    # Get transfer recommendations
    transfer_recs = transfer_optimizer.get_transfer_recommendations(
        current_squad,
        expected_points,
        free_transfers=user_team_config.free_transfers,
        budget_remaining=user_team_config.bank,
        max_suggestions=5
    )

    if transfer_recs:
        print("\n  Transfer Recommendations:")
        print("  " + "=" * 76)
        for rec in transfer_recs[:3]:
            print(f"\n  #{rec['rank']}: {rec['player_out']['name']} → {rec['player_in']['name']}")
            print(f"    Out: {rec['player_out']['team']} £{rec['player_out']['price']}m "
                  f"(EP: {rec['player_out']['expected_points']:.1f})")
            print(f"    In:  {rec['player_in']['team']} £{rec['player_in']['price']}m "
                  f"(EP: {rec['player_in']['expected_points']:.1f})")
            print(f"    Value: +{rec['value']:.1f} points | "
                  f"Cost: £{rec['price_change']:+.1f}m | "
                  f"Worth hit: {'YES' if rec['worth_hit'] else 'NO'}")
            print(f"    Reasons: {', '.join(rec['reasons'])}")
    else:
        print("  - No valuable transfers identified - hold transfers")

    # Multi-week transfer plan
    print("\n  Multi-Week Transfer Plan:")
    transfer_plan = transfer_optimizer.optimize_multi_week_transfers(
        current_squad,
        expected_points_by_week,
        free_transfers=user_team_config.free_transfers,
        budget_remaining=user_team_config.bank,
        planning_horizon=config.transfer_planning_horizon
    )

    for gw, plan in list(transfer_plan.items())[:config.transfer_planning_horizon]:
        print(f"\n  GW{gw}: {plan['action']}")
        if plan['transfers']:
            for t in plan['transfers']:
                print(f"    {t['out']} → {t['in']} (Value: +{t['value']:.1f})")

    # Chip strategy
    if config.plan_chips:
        print(f"\n  Analyzing chip strategy...")
        chip_optimizer = ChipStrategyOptimizer(gameweek_data)

        chip_strategy = chip_optimizer.get_chip_strategy(
            current_squad,
            expected_points_by_week,
            available_chips=user_team_config.chips_available,
            horizon=config.chip_planning_horizon
        )

        print("\n  Chip Recommendations:")
        print("  " + "=" * 76)

        for chip_name, strategy in chip_strategy.items():
            print(f"\n  {chip_name.upper().replace('_', ' ')}:")
            print(f"    Best gameweek: GW{strategy['best_gameweek']}")
            print(f"    Expected value: +{strategy['best_value']:.1f} points")
            print(f"    Recommended: {'YES' if strategy['recommended'] else 'NO'}")

            if chip_name == 'triple_captain' and 'best_captain' in strategy:
                print(f"    Best captain: {strategy['best_captain']}")

    # Starting XI for current week
    step_num = 6 if user_team_config.team_id else 5
    print(f"\n[{step_num}/6] Optimizing starting XI for GW{gameweek_data.current_gameweek}...")
    optimizer = SquadOptimizer(gameweek_data)
    starting_result = optimizer.optimize_starting_xi(
        current_squad,
        expected_points,
        verbose=False
    )

    if starting_result:
        captain = gameweek_data.get_player_by_id(starting_result['captain'])
        print(f"  - Captain: {captain.name}")
        print(f"  - Expected points: {starting_result['total_expected_points']:.2f}")

        optimizer.display_squad(
            current_squad,
            expected_points,
            starting_xi=starting_result['starting_xi'],
            captain_id=starting_result['captain']
        )

    print("\n" + "=" * 80)
    print("Advanced optimization complete!")
    print("=" * 80)


def main():
    """Main entry point with command-line arguments."""
    parser = argparse.ArgumentParser(description='FPL Optimizer')
    parser.add_argument(
        '--mode',
        choices=['basic', 'advanced'],
        default='basic',
        help='Optimization mode (default: basic)'
    )
    parser.add_argument(
        '--preset',
        choices=['conservative', 'balanced', 'aggressive'],
        default='balanced',
        help='Strategy preset (default: balanced)'
    )
    parser.add_argument(
        '--team-id',
        type=int,
        help='Your FPL team ID (for advanced mode)'
    )
    parser.add_argument(
        '--free-transfers',
        type=int,
        help='Number of free transfers available (overrides API detection)'
    )
    parser.add_argument(
        '--bank',
        type=float,
        help='Money in bank in millions (e.g., 1.8 for £1.8m)'
    )

    args = parser.parse_args()

    # Get configuration
    config = get_config(args.preset)
    user_team_config = UserTeamConfig(team_id=args.team_id)

    # Apply manual overrides if provided
    if args.free_transfers is not None:
        user_team_config.free_transfers = args.free_transfers
    if args.bank is not None:
        user_team_config.bank = args.bank

    # Run optimizer
    if args.mode == 'basic':
        run_basic_optimizer(config)
    else:
        run_advanced_optimizer(config, user_team_config)


if __name__ == "__main__":
    main()
