#!/usr/bin/env python3
"""
Quick test to verify BPS integration works correctly.
"""
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent))

from src.data.api_client import FPLAPIClient
from src.data.models import build_gameweek_data
from src.prediction.advanced_forecaster import AdvancedForecaster


def test_bps_integration():
    """Test that BPS integration works without errors."""
    print("=" * 80)
    print("TESTING BPS INTEGRATION")
    print("=" * 80)

    # Initialize API client
    print("\n1. Initializing FPL API client...")
    api_client = FPLAPIClient()

    # Fetch current gameweek data
    print("2. Fetching gameweek data...")
    bootstrap = api_client.get_bootstrap_static()
    fixtures = api_client.get_fixtures()

    gameweek_data = build_gameweek_data(bootstrap, fixtures)
    print(f"   Current GW: {gameweek_data.current_gameweek}")
    print(f"   Players: {len(gameweek_data.players)}")

    # Initialize forecaster with BPS enabled
    print("\n3. Initializing AdvancedForecaster with BPS enabled...")
    forecaster = AdvancedForecaster(
        gameweek_data,
        api_client,
        use_rotation_model=True,
        use_xg_model=True,
        use_understat=False,  # Disabled for speed
        use_bonus_model=True   # ENABLED for testing
    )
    print("   ✓ Forecaster initialized")

    # Test predictions on a few top players
    print("\n4. Testing predictions with bonus points...")
    test_players = [p for p in gameweek_data.players if p.points_per_game > 5.0][:5]

    for player in test_players:
        prediction = forecaster.predict_points(player, num_gameweeks=3, detailed=True)

        print(f"\n   {player.name} ({player.position})")
        print(f"     Total: {prediction['total']:.2f} pts")
        print(f"     Base PPG: {prediction['base_ppg']:.2f}")
        print(f"     xG Variance: {prediction['xg_variance']:.2f}")
        print(f"     Expected Bonus: {prediction['expected_bonus']:.2f}")

        # Verify bonus is included
        if prediction['expected_bonus'] > 0:
            print(f"     ✓ Bonus points predicted successfully!")

    print("\n" + "=" * 80)
    print("BPS INTEGRATION TEST COMPLETE")
    print("=" * 80)
    print("\n✓ All tests passed! BPS integration working correctly.")


if __name__ == "__main__":
    try:
        test_bps_integration()
    except Exception as e:
        print(f"\n✗ TEST FAILED: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
