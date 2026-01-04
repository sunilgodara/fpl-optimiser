"""
Main entry point for FPL Optimizer.
"""
from data.api_client import FPLAPIClient
from data.models import build_gameweek_data
from prediction.forecaster import PointForecaster
from optimization.squad_optimizer import SquadOptimizer


def main():
    """Run the FPL optimizer pipeline."""
    print("=" * 80)
    print("FPL OPTIMIZER - Fantasy Premier League Squad Optimizer")
    print("=" * 80)

    # Step 1: Fetch data from FPL API
    print("\n[1/5] Fetching data from FPL API...")
    api_client = FPLAPIClient()
    gameweek_data = build_gameweek_data(api_client)

    print(f"  - Loaded {len(gameweek_data.players)} players")
    print(f"  - Loaded {len(gameweek_data.teams)} teams")
    print(f"  - Loaded {len(gameweek_data.fixtures)} upcoming fixtures")
    print(f"  - Current gameweek: {gameweek_data.current_gameweek}")

    # Step 2: Predict player points
    print("\n[2/5] Predicting player points based on form and fixtures...")
    forecaster = PointForecaster(gameweek_data)

    # Predict for next 3 gameweeks
    num_gameweeks = 3
    expected_points = forecaster.get_predictions_for_all_players(
        num_gameweeks=num_gameweeks
    )

    print(f"  - Generated predictions for next {num_gameweeks} gameweeks")

    # Show top predicted players by position
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

    # Step 3: Optimize squad
    print("\n[3/5] Optimizing squad selection...")
    optimizer = SquadOptimizer(gameweek_data)

    squad_result = optimizer.optimize_squad(expected_points, verbose=False)

    if not squad_result:
        print("ERROR: Squad optimization failed!")
        return

    print(f"  - Squad optimized successfully!")
    print(f"  - Total expected points: {squad_result['total_expected_points']:.2f}")
    print(f"  - Total cost: £{squad_result['total_cost']:.1f}m")

    # Step 4: Optimize starting XI
    print("\n[4/5] Optimizing starting XI and captain selection...")
    starting_result = optimizer.optimize_starting_xi(
        squad_result['squad'],
        expected_points,
        verbose=False
    )

    if not starting_result:
        print("ERROR: Starting XI optimization failed!")
        return

    captain = gameweek_data.get_player_by_id(starting_result['captain'])
    print(f"  - Starting XI optimized!")
    print(f"  - Captain: {captain.name}")
    print(f"  - Total expected points (with captain): "
          f"{starting_result['total_expected_points']:.2f}")

    # Step 5: Display results
    print("\n[5/5] Final Results:")
    optimizer.display_squad(
        squad_result['squad'],
        expected_points,
        starting_xi=starting_result['starting_xi'],
        captain_id=starting_result['captain']
    )

    # Bench players
    bench = [
        pid for pid in squad_result['squad']
        if pid not in starting_result['starting_xi']
    ]
    print("\nBENCH:")
    print("-" * 80)
    for pid in bench:
        player = gameweek_data.get_player_by_id(pid)
        team = gameweek_data.get_team_by_id(player.team_id)
        ep = expected_points.get(pid, 0)
        print(f"  {player.name:20} ({player.position}) | {team.short_name:4} | "
              f"£{player.price:4.1f}m | EP: {ep:5.2f}")

    print("\n" + "=" * 80)
    print("Optimization complete!")
    print("=" * 80)


if __name__ == "__main__":
    main()
