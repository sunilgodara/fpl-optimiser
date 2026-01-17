#!/usr/bin/env python3
"""Debug script to check predictions for specific players."""

from src.data.api_client import FPLAPIClient
from src.data.models import build_gameweek_data
from src.prediction.advanced_forecaster import AdvancedForecaster

# Initialize
api_client = FPLAPIClient()
gameweek_data = build_gameweek_data(api_client)
forecaster = AdvancedForecaster(gameweek_data, api_client, use_understat=False)

# Find elite players by name
player_names = [
    'Salah', 'Haaland', 'Palmer', 'Saka', 'Son',
    'Alexander-Arnold', 'Bruno', 'Isak', 'Watkins',
    'Thiago', 'Collins', 'Aaronson', 'Mané', 'Garner'
]

print("=" * 80)
print("PREDICTION DEBUG - Elite vs Budget Players")
print("=" * 80)

for name in player_names:
    # Find player
    matches = [p for p in gameweek_data.players if name.lower() in p.name.lower()]

    if not matches:
        print(f"\n❌ {name}: Not found")
        continue

    player = matches[0]

    # Get detailed prediction
    detailed = forecaster.predict_points(player, num_gameweeks=1, detailed=True)

    print(f"\n{'=' * 80}")
    print(f"{player.name} (£{player.price}m, {player.position})")
    print(f"{'=' * 80}")
    print(f"  1-GW Prediction: {detailed['total']:.2f} pts")
    print(f"  Form score: {detailed['form_score']:.2f}")
    print(f"  PPG score: {player.points_per_game:.2f}")
    print(f"  Base PPG: {detailed['base_ppg']:.2f}")
    print(f"  Fixture mult: {detailed['fixture_mult']:.2f}x")
    print(f"  Minutes reliability: {detailed['minutes_reliability']:.2f}")
    print(f"  Consistency: {detailed['consistency']:.2f}")
    print(f"  Rotation risk: {detailed['rotation_risk']:.3f}")
    print(f"  Expected bonus: {detailed['expected_bonus']:.2f}")
    print(f"  Status: {player.status} (available: {player.is_available()})")

    # Calculate what they'd get over 5 GWs
    gw5_pred = detailed['total'] * 5
    print(f"  5-GW projection: {gw5_pred:.1f} pts ({detailed['total']:.1f}/GW)")

print(f"\n{'=' * 80}")
print("SUMMARY")
print(f"{'=' * 80}")
