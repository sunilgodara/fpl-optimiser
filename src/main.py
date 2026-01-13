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
from .optimization.long_term_optimizer import LongTermOptimizer, SeasonPlan
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
        forecaster = AdvancedForecaster(gameweek_data, api_client, use_understat=False)
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
    squad_result = optimizer.optimize_squad(
        expected_points,
        verbose=False,
        differential_weight=config.differential_weight
    )

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
    vice_captain = gameweek_data.get_player_by_id(starting_result['vice_captain']) if starting_result.get('vice_captain') else None

    print(f"  - Captain: {captain.name}")
    if vice_captain:
        print(f"  - Vice-Captain: {vice_captain.name} (backup if captain doesn't play)")
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


def run_long_term_optimizer(config, user_team_config, args):
    """Run long-term season optimization (maximizes cumulative points GW N→38)."""
    print("=" * 80)
    print("FPL OPTIMIZER - LONG-TERM SEASON PLANNING")
    print("Maximizing cumulative points from now through GW38")
    print("=" * 80)

    # Fetch data
    print("\n[1/5] Fetching data from FPL API...")
    api_client = FPLAPIClient()
    gameweek_data = build_gameweek_data(api_client)
    next_gw = api_client.get_next_gameweek()
    if next_gw is None:
        next_gw = gameweek_data.current_gameweek

    print(f"  - Current gameweek: {gameweek_data.current_gameweek}")
    print(f"  - Planning from: GW{next_gw} → GW38")
    print(f"  - Remaining gameweeks: {38 - next_gw + 1}")

    # Fetch user's team
    if user_team_config.team_id:
        print(f"\n[2/5] Fetching your FPL team (ID: {user_team_config.team_id})...")
        team_data = api_client.get_team_current_squad(user_team_config.team_id)
        if team_data:
            user_team_config.current_squad = team_data['squad']
            user_team_config.player_values = team_data.get('player_values', {})

            if args.bank is None:
                user_team_config.bank = team_data['bank']
            if args.free_transfers is None:
                user_team_config.free_transfers = team_data.get('free_transfers', 1)

            print(f"  - Manager: {team_data['player_name']}")
            print(f"  - Overall Rank: {team_data['overall_rank']:,}")
            print(f"  - Squad Value: £{team_data['squad_value']:.1f}m")
            print(f"  - Bank: £{user_team_config.bank:.1f}m")
            print(f"  - Free Transfers: {user_team_config.free_transfers}")
            print(f"  - Chips Available: {', '.join(user_team_config.chips_available) or 'None'}")
        else:
            print("  - Could not fetch team data")
            return None
    else:
        print("\n⚠️  ERROR: Long-term optimization requires --team-id parameter")
        print("Example: python -m src.main --mode advanced --long-term --team-id 123456")
        return None

    # Generate multi-week predictions
    print(f"\n[3/5] Generating predictions for next {config.chip_planning_horizon} gameweeks...")
    use_understat = args.use_understat if hasattr(args, 'use_understat') else False
    if use_understat:
        print("  ⚠️  Understat enabled - this will take 10-15 minutes per gameweek")
    forecaster = AdvancedForecaster(gameweek_data, api_client, use_understat=use_understat)

    expected_points_by_week = {}
    for gw_offset in range(min(config.chip_planning_horizon, 38 - next_gw + 1)):
        gw = next_gw + gw_offset
        ep = forecaster.get_predictions_for_all_players(num_gameweeks=1)
        expected_points_by_week[gw] = ep

    print(f"  - Generated predictions for GW{next_gw} through GW{next_gw + len(expected_points_by_week) - 1}")

    # Run long-term optimization
    print(f"\n[4/5] Running long-term optimization...")
    print("  - Optimizing transfer sequences over full horizon")
    print("  - Finding globally optimal chip timing")
    print("  - Considering future fixtures and form trends")

    long_term_opt = LongTermOptimizer(
        gameweek_data=gameweek_data,
        current_squad=user_team_config.current_squad,
        bank=user_team_config.bank,
        free_transfers=user_team_config.free_transfers,
        chips_available=user_team_config.chips_available
    )

    season_plan = long_term_opt.optimize_season(
        expected_points_by_week=expected_points_by_week,
        horizon=min(10, 38 - next_gw + 1),  # Plan next 10 GWs in detail
        strategy='cumulative_points'
    )

    print(f"  ✓ Optimization complete!")

    # Display results
    print(f"\n[5/5] Season Plan Results:")
    print("=" * 80)
    print(season_plan.reasoning)
    print("=" * 80)

    # Show immediate action (next GW)
    if season_plan.decisions:
        next_decision = season_plan.decisions[0]
        print(f"\n🎯 IMMEDIATE ACTION FOR GW{next_decision.gameweek}:")
        print("-" * 80)

        if next_decision.chip_used:
            chip_display = {
                'wildcard': '🃏 WILDCARD',
                'freehit': '⚡ FREE HIT',
                'bboost': '💪 BENCH BOOST',
                '3xc': '👑 TRIPLE CAPTAIN'
            }.get(next_decision.chip_used, next_decision.chip_used.upper())
            print(f"  Chip: {chip_display}")

        if next_decision.transfers_in:
            print(f"\n  Transfers ({len(next_decision.transfers_in)}):")
            for i, (out_id, in_id) in enumerate(zip(next_decision.transfers_out, next_decision.transfers_in), 1):
                out_player = gameweek_data.get_player_by_id(out_id)
                in_player = gameweek_data.get_player_by_id(in_id)
                print(f"    {i}. OUT: {out_player.name:20} → IN: {in_player.name:20}")

            if next_decision.hits_taken > 0:
                print(f"\n  Cost: {next_decision.hits_taken} hit(s) = -{next_decision.hits_taken * 4} points")
        else:
            print("  No transfers recommended - hold your free transfer")

        print(f"\n  Expected Points: {next_decision.expected_points:.1f}")
        print(f"  Bank After: £{next_decision.bank_after:.1f}m")
        print(f"  Free Transfers Next Week: {next_decision.free_transfers_after}")

    # Detailed gameweek breakdown
    print(f"\n\n📅 DETAILED GAMEWEEK PLAN:")
    print("=" * 80)

    for i, decision in enumerate(season_plan.decisions[:10], 1):  # Show first 10 GWs
        print(f"\nGW{decision.gameweek}:")

        if decision.chip_used:
            chip_name = decision.chip_used.upper().replace('BBOOST', 'BENCH BOOST').replace('3XC', 'TRIPLE CAPTAIN')
            print(f"  Chip: {chip_name}")

        if decision.transfers_in:
            print(f"  Transfers: {len(decision.transfers_in)} player(s)")
            if decision.hits_taken > 0:
                print(f"  Hits: -{decision.hits_taken * 4} points")
        else:
            print(f"  Transfers: None (banking FT)")

        print(f"  Expected Points: {decision.expected_points:.1f}")
        print(f"  Bank: £{decision.bank_after:.1f}m | FTs Next: {decision.free_transfers_after}")

    if len(season_plan.decisions) > 10:
        print(f"\n  ... (+ {len(season_plan.decisions) - 10} more gameweeks in plan)")

    # Summary stats
    print(f"\n\n📊 SEASON PLAN SUMMARY:")
    print("=" * 80)
    print(f"  Total Expected Points: {season_plan.total_expected_points:.1f}")
    print(f"  Total Transfer Hits: {season_plan.total_transfer_cost} hits (- {season_plan.total_transfer_cost} points)")
    print(f"  Net Expected Points: {season_plan.net_expected_points:.1f}")
    print(f"  Average Points/GW: {season_plan.net_expected_points / len(season_plan.decisions):.1f}")

    if season_plan.chip_schedule:
        print(f"\n  Chips Scheduled:")
        for chip, gw in sorted(season_plan.chip_schedule.items(), key=lambda x: x[1]):
            chip_display = chip.replace('_', ' ').title()
            print(f"    - GW{gw}: {chip_display}")

    print("\n" + "=" * 80)
    print("Long-term optimization complete!")
    print("=" * 80)

    return season_plan


def run_advanced_optimizer(config, user_team_config, args):
    """Run advanced optimization with transfers and chip strategy."""
    print("=" * 80)
    print("FPL OPTIMIZER - Advanced Strategy Planning")
    print("=" * 80)

    # Fetch data
    print("\n[1/6] Fetching data from FPL API...")
    api_client = FPLAPIClient()
    gameweek_data = build_gameweek_data(api_client)

    # Get the next gameweek for planning (the one with the upcoming deadline)
    next_gw = api_client.get_next_gameweek()
    if next_gw is None:
        next_gw = gameweek_data.current_gameweek

    print(f"  - Loaded {len(gameweek_data.players)} players")
    print(f"  - Current gameweek: {gameweek_data.current_gameweek}")
    print(f"  - Planning for: GW{next_gw} (next deadline)")

    # Show differential strategy status (Phase 3: Issue #9)
    if config.differential_weight > 0:
        if config.differential_weight >= 0.2:
            strategy_label = "AGGRESSIVE differential hunting"
        elif config.differential_weight >= 0.1:
            strategy_label = "Moderate differential strategy"
        else:
            strategy_label = "Light differential weighting"
        print(f"  - Strategy: {strategy_label} (weight: {config.differential_weight})")
        print(f"    └─ Low-ownership players will get bonus weighting for rank climbing")

    # Fetch user's team if team_id provided
    if user_team_config.team_id:
        print(f"\n[2/6] Fetching your FPL team (ID: {user_team_config.team_id})...")
        team_data = api_client.get_team_current_squad(user_team_config.team_id)
        if team_data:
            user_team_config.current_squad = team_data['squad']

            # Store player values (purchase and selling prices)
            user_team_config.player_values = team_data.get('player_values', {})
            user_team_config.total_selling_value = team_data.get('total_selling_value', 0.0)
            user_team_config.locked_value = team_data.get('locked_value', 0.0)

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
            print(f"  - Bank: £{user_team_config.bank:.1f}m{' (manual override)' if args.bank is not None else ''} (liquid)")

            # Show value breakdown
            if user_team_config.locked_value > 0.01:  # Only show if significant
                total_available = user_team_config.bank + user_team_config.total_selling_value
                print(f"  - Locked Value: £{user_team_config.locked_value:.1f}m (profit locked in players)")
                print(f"  - Total Budget Available: £{total_available:.1f}m (if you sell all players)")

            print(f"  - Free Transfers: {user_team_config.free_transfers}{' (manual override)' if args.free_transfers is not None else ' (API estimate - may be inaccurate)'}")

            if args.free_transfers is None and team_data.get('transfers_made_this_week', 0) == 0:
                print(f"  - Note: No transfers made in GW{gameweek_data.current_gameweek}. You likely have 2+ free transfers.")
                print(f"           Use --free-transfers to specify exact count (e.g., --free-transfers 5)")
        else:
            print(f"  - Could not fetch team data. Will optimize new squad.")

    # Advanced predictions
    print(f"\n[{'3' if user_team_config.team_id else '2'}/6] Generating advanced predictions...")
    use_understat = args.use_understat if hasattr(args, 'use_understat') else False
    if use_understat:
        print("  ⚠️  Understat enabled - this will take 10-15 minutes per gameweek")
    forecaster = AdvancedForecaster(gameweek_data, api_client, use_understat=use_understat)

    # Generate predictions for multiple gameweeks starting from next gameweek
    expected_points_by_week = {}
    for gw_offset in range(config.chip_planning_horizon):
        gw = next_gw + gw_offset
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
        squad_result = optimizer.optimize_squad(
            expected_points,
            verbose=False,
            differential_weight=config.differential_weight
        )
        if not squad_result:
            print("ERROR: Squad optimization failed!")
            return None
        current_squad = squad_result['squad']
        print(f"  - Optimized squad: {squad_result['total_expected_points']:.2f} EP")

    # Chip strategy - EVALUATE FIRST (Phase 1 Fix #3)
    step_num = 5 if user_team_config.team_id else 4
    wildcard_recommended_for_next_gw = False
    chip_strategy = None

    if config.plan_chips:
        print(f"\n[{step_num}/6] Analyzing chip strategy...")
        chip_optimizer = ChipStrategyOptimizer(gameweek_data)

        chip_strategy = chip_optimizer.get_chip_strategy(
            current_squad,
            expected_points_by_week,
            available_chips=user_team_config.chips_available,
            horizon=config.chip_planning_horizon
        )

        # Check if Wildcard is recommended for next gameweek
        if 'wildcard' in chip_strategy:
            wildcard_gw = chip_strategy['wildcard']['best_gameweek']
            if wildcard_gw == next_gw and chip_strategy['wildcard']['recommended']:
                wildcard_recommended_for_next_gw = True

    # Transfer planning - CONDITIONAL ON CHIP DECISION
    step_num = 6 if user_team_config.team_id else 5
    print(f"\n[{step_num}/6] Planning strategy for GW{next_gw}...")
    transfer_optimizer = TransferOptimizer(gameweek_data)

    # SCENARIO-BASED RECOMMENDATIONS
    squad_for_starting_xi = current_squad  # Default to current squad
    scenario_used = "current"  # Track which scenario is being shown

    if wildcard_recommended_for_next_gw:
        print("\n" + "=" * 80)
        print("WILDCARD RECOMMENDED FOR GW{next_gw}".format(next_gw=next_gw))
        print("Showing 2 scenarios for your decision:")
        print("=" * 80)

        # Scenario A: Use Wildcard
        print(f"\n📋 SCENARIO A: Use Wildcard in GW{next_gw}")
        print("-" * 80)
        print("With Wildcard, you can rebuild your entire 15-man squad from scratch.")

        # Optimize squad with wildcard (unlimited transfers)
        optimizer = SquadOptimizer(gameweek_data)
        wildcard_squad = optimizer.optimize_squad(
            expected_points,
            verbose=False,
            differential_weight=config.differential_weight
        )

        if wildcard_squad:
            print(f"  Expected value: +{chip_strategy['wildcard']['best_value']:.1f} points")
            print(f"  Total squad expected points: {wildcard_squad['total_expected_points']:.2f}")
            print(f"  Squad cost: £{wildcard_squad['total_cost']:.1f}m")

            # Use wildcard squad for final starting XI (since it's recommended)
            squad_for_starting_xi = wildcard_squad['squad']
            scenario_used = "wildcard"

        # Scenario B: Don't use Wildcard (regular transfers)
        print(f"\n📋 SCENARIO B: Save Wildcard, make regular transfers")
        print("-" * 80)

        transfer_recs = transfer_optimizer.get_transfer_recommendations(
            current_squad,
            expected_points,
            free_transfers=user_team_config.free_transfers,
            budget_remaining=user_team_config.bank,
            max_suggestions=5,
            player_values=user_team_config.player_values
        )

        if transfer_recs:
            num_free = user_team_config.free_transfers
            num_shown = min(len(transfer_recs), num_free, 5)
            print(f"  You have {num_free} free transfer{'s' if num_free != 1 else ''}. Best {num_shown} transfer{'s' if num_shown != 1 else ''} for GW{next_gw}:")
            for rec in transfer_recs[:num_shown]:
                print(f"\n  #{rec['rank']}: {rec['player_out']['name']} → {rec['player_in']['name']}")
                print(f"    Value: +{rec['value']:.1f} points | Cost: £{rec['price_change']:+.1f}m")
        else:
            print("  - No valuable transfers identified")

        print("\n" + "=" * 80)
        print(f"💡 RECOMMENDATION: Scenario A (Wildcard) offers +{chip_strategy['wildcard']['best_value']:.1f} points value")
        print("=" * 80)

    else:
        # No Wildcard for next GW - show regular transfers
        print("\n  Transfer Recommendations:")
        print("  " + "=" * 76)

        transfer_recs = transfer_optimizer.get_transfer_recommendations(
            current_squad,
            expected_points,
            free_transfers=user_team_config.free_transfers,
            budget_remaining=user_team_config.bank,
            max_suggestions=5,
            player_values=user_team_config.player_values
        )

        if transfer_recs:
            num_free = user_team_config.free_transfers
            num_shown = min(len(transfer_recs), num_free, 5)
            print(f"  You have {num_free} free transfer{'s' if num_free != 1 else ''}. Best {num_shown} transfer{'s' if num_shown != 1 else ''} for GW{next_gw}:")
            print()
            for rec in transfer_recs[:num_shown]:
                print(f"  #{rec['rank']}: {rec['player_out']['name']} → {rec['player_in']['name']}")
                print(f"    Out: {rec['player_out']['team']} £{rec['player_out']['price']}m "
                      f"(EP: {rec['player_out']['expected_points']:.1f})")
                print(f"    In:  {rec['player_in']['team']} £{rec['player_in']['price']}m "
                      f"(EP: {rec['player_in']['expected_points']:.1f})")
                print(f"    Value: +{rec['value']:.1f} points | "
                      f"Cost: £{rec['price_change']:+.1f}m | "
                      f"Worth hit: {'YES' if rec['worth_hit'] else 'NO'}")
                print(f"    Reasons: {', '.join(rec['reasons'])}")
                print()
        else:
            print("  - No valuable transfers identified - hold transfers")

        # Multi-week transfer plan
        print("\n  Multi-Week Transfer Plan:")
        transfer_plan = transfer_optimizer.optimize_multi_week_transfers(
            current_squad,
            expected_points_by_week,
            free_transfers=user_team_config.free_transfers,
            budget_remaining=user_team_config.bank,
            planning_horizon=config.transfer_planning_horizon,
            player_values=user_team_config.player_values
        )

        for gw, plan in list(transfer_plan.items())[:config.transfer_planning_horizon]:
            print(f"\n  GW{gw}: {plan['action']}")
            if plan['transfers']:
                for t in plan['transfers']:
                    print(f"    {t['out']} → {t['in']} (Value: +{t['value']:.1f})")

    # Chip strategy summary (if not already shown above)
    if config.plan_chips and chip_strategy:
        print("\n  Full Chip Strategy Overview:")
        print("  " + "=" * 76)
        print("  Note: Only ONE chip can be used per gameweek (FPL rules)")

        # Check for conflicts
        has_conflicts = '_conflicts' in chip_strategy

        for chip_name, strategy in chip_strategy.items():
            # Skip metadata keys
            if chip_name.startswith('_'):
                continue

            print(f"\n  {chip_name.upper().replace('_', ' ')}:")
            print(f"    Best gameweek: GW{strategy['best_gameweek']}")
            print(f"    Expected value: +{strategy['best_value']:.1f} points")
            print(f"    Recommended: {'YES' if strategy['recommended'] else 'NO'}")

            # Show conflict resolution info
            if 'conflict_resolution' in strategy:
                print(f"    ⚠️  {strategy['conflict_resolution']}")
                print(f"    (Originally recommended for GW{strategy['original_gameweek']})")

            if chip_name == 'triple_captain' and 'best_captain' in strategy:
                print(f"    Best captain: {strategy['best_captain']}")

        # Show rejected chips due to conflicts
        if has_conflicts and 'rejected_chips' in chip_strategy['_conflicts']:
            rejected = chip_strategy['_conflicts']['rejected_chips']
            if rejected:
                print(f"\n  ⚠️  Conflict Warning:")
                for chip in rejected:
                    print(f"    - {chip['chip_name'].upper().replace('_', ' ')}: Could not be scheduled")
                    print(f"      (Wanted GW{chip['original_gw']}, but higher-value chip takes priority)")

    # Starting XI for next week
    final_step = 7 if user_team_config.team_id else 6
    if scenario_used == "wildcard":
        print(f"\n[{final_step}/{final_step}] Optimizing starting XI for GW{next_gw} (Wildcard Squad - Scenario A)...")
    else:
        print(f"\n[{final_step}/{final_step}] Optimizing starting XI for GW{next_gw} (Current Squad)...")

    optimizer = SquadOptimizer(gameweek_data)
    starting_result = optimizer.optimize_starting_xi(
        squad_for_starting_xi,
        expected_points,
        verbose=False
    )

    if starting_result:
        captain = gameweek_data.get_player_by_id(starting_result['captain'])
        vice_captain = gameweek_data.get_player_by_id(starting_result['vice_captain']) if starting_result.get('vice_captain') else None

        print(f"  - Captain: {captain.name}")
        if vice_captain:
            print(f"  - Vice-Captain: {vice_captain.name} (backup if captain doesn't play)")
        print(f"  - Expected points: {starting_result['total_expected_points']:.2f}")

        if scenario_used == "wildcard":
            print(f"  - Note: This is the optimal starting XI from the Wildcard squad (Scenario A)")

        optimizer.display_squad(
            squad_for_starting_xi,
            expected_points,
            starting_xi=starting_result['starting_xi'],
            captain_id=starting_result['captain']
        )

        # Captaincy analysis (Phase 3: Issue #10)
        print("\n" + "="*80)
        print("CAPTAINCY OPTIONS")
        print("="*80)

        captaincy_options = optimizer.get_captaincy_options(
            squad_for_starting_xi,
            expected_points,
            num_options=3
        )

        for option in captaincy_options:
            print(f"\n{option['risk_color']} Option #{option['rank']}: {option['name']} ({option['team']}) - {option['risk_profile']}")
            print(f"   Expected Points: {option['expected_points']:.1f} | Ownership: {option['ownership']:.1f}%")
            print(f"   {option['recommendation']}")
            print(f"   Reasons:")
            for reason in option['reasons']:
                print(f"     • {reason}")

        print("="*80)

        # Template awareness (Phase 3: Issue #12)
        print("\n" + "="*80)
        print("TEMPLATE ANALYSIS")
        print("="*80)

        template_analysis = optimizer.analyze_template_matching(
            squad_for_starting_xi,
            ownership_threshold=30.0
        )

        print(f"\nYour squad matches {template_analysis['template_match_pct']:.1f}% of the template")
        print(f"Template Players in Squad: {template_analysis['template_count']}/{template_analysis['template_total']}")
        print(f"Average Squad Ownership: {template_analysis['avg_ownership']:.1f}%")

        if template_analysis['template_match_pct'] < 50:
            print("\n⚠️  Low template match - high risk/high reward strategy")
        elif template_analysis['template_match_pct'] < 70:
            print("\n✓ Balanced approach - some template, some differentials")
        else:
            print("\n✓ Template squad - safe for rank protection")

        if template_analysis['template_in_squad']:
            print("\n📊 Template Players You Own:")
            for player in template_analysis['template_in_squad'][:5]:
                print(f"   {player['name']:20} ({player['team']:4}) - {player['ownership']:.1f}% owned")

        if template_analysis['template_missing']:
            print("\n⚠️  High Ownership Players You're Missing:")
            for player in template_analysis['template_missing'][:5]:
                print(f"   {player['name']:20} ({player['team']:4}) - {player['ownership']:.1f}% owned")

        if template_analysis['differentials']:
            print("\n🎯 Your Differential Picks (<10% owned):")
            for player in template_analysis['differentials'][:5]:
                print(f"   {player['name']:20} ({player['team']:4}) - {player['ownership']:.1f}% owned")

        print("="*80)

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
    parser.add_argument(
        '--long-term',
        action='store_true',
        help='Enable long-term season optimization (GW N→38 planning)'
    )
    parser.add_argument(
        '--use-understat',
        action='store_true',
        help='Enable real xG data from Understat (slower but more accurate, adds ~10-15 min)'
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
    elif args.long_term:
        # Long-term season optimization mode
        run_long_term_optimizer(config, user_team_config, args)
    else:
        # Standard advanced mode
        run_advanced_optimizer(config, user_team_config, args)


if __name__ == "__main__":
    main()
