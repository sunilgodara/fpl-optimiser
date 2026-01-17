"""
Enhanced explanations and transparency for FPL optimizer recommendations.

Provides clear, detailed reasoning for all decisions with confidence levels.
"""
from typing import Dict, List, Optional, Tuple
from ..data.models import Player, Team


class RecommendationExplainer:
    """
    Generates human-readable explanations for optimizer recommendations.
    """

    def __init__(self, gameweek_data):
        self.data = gameweek_data

    def explain_transfer(
        self,
        player_in: Player,
        player_out: Player,
        transfer_value: Dict,
        confidence: float
    ) -> str:
        """
        Generate detailed explanation for a transfer recommendation.

        Args:
            player_in: Incoming player
            player_out: Outgoing player
            transfer_value: TransferValue breakdown
            confidence: Confidence score (0-1)

        Returns:
            Formatted explanation string
        """
        explanation = []
        explanation.append(f"\n{'=' * 70}")
        explanation.append(f"TRANSFER RECOMMENDATION")
        explanation.append(f"{'=' * 70}")

        # Header
        explanation.append(f"\nOUT: {player_out.name} ({player_out.position}, £{player_out.price}m)")
        explanation.append(f"IN:  {player_in.name} ({player_in.position}, £{player_in.price}m)")

        # Confidence indicator
        if confidence >= 0.8:
            confidence_label = "🟢 HIGH CONFIDENCE"
        elif confidence >= 0.6:
            confidence_label = "🟡 MEDIUM CONFIDENCE"
        else:
            confidence_label = "🟠 LOW CONFIDENCE"

        explanation.append(f"\nConfidence: {confidence_label} ({confidence:.0%})")

        # Value breakdown
        explanation.append(f"\n--- VALUE BREAKDOWN ---")
        explanation.append(f"Expected Points Gain: +{transfer_value['points_gain']:.1f} pts (over {transfer_value['fixture_swing_duration']} GWs)")

        if transfer_value['price_change_value'] > 0:
            explanation.append(f"Price Change Value: +{transfer_value['price_change_value']:.1f} pts")

        if transfer_value['flexibility_value'] > 0:
            explanation.append(f"Squad Flexibility: +{transfer_value['flexibility_value']:.1f} pts")

        if transfer_value['chip_synergy_value'] != 0:
            explanation.append(f"Chip Synergy: {transfer_value['chip_synergy_value']:+.1f} pts")

        if transfer_value['transfer_cost'] < 0:
            explanation.append(f"Transfer Cost: {transfer_value['transfer_cost']:.1f} pts (-4 hit)")

        explanation.append(f"\nTOTAL VALUE: {transfer_value['total_value']:+.1f} pts")

        # Reasoning
        explanation.append(f"\n--- WHY THIS TRANSFER? ---")

        # Points gain reasoning
        if transfer_value['points_gain'] > 10:
            explanation.append(f"✓ Large points advantage ({transfer_value['points_gain']:.1f} pts)")
        elif transfer_value['points_gain'] > 5:
            explanation.append(f"✓ Moderate points advantage ({transfer_value['points_gain']:.1f} pts)")
        else:
            explanation.append(f"• Small points advantage ({transfer_value['points_gain']:.1f} pts)")

        # Fixture swing
        if transfer_value['fixture_swing_duration'] >= 4:
            explanation.append(f"✓ Extended fixture advantage ({transfer_value['fixture_swing_duration']} GWs)")
        elif transfer_value['fixture_swing_duration'] >= 2:
            explanation.append(f"• Moderate fixture run ({transfer_value['fixture_swing_duration']} GWs)")

        # Price changes
        if transfer_value['price_change_value'] > 1:
            explanation.append(f"✓ Likely price rise for {player_in.name}")

        # Payback period
        payback = transfer_value.get('payback_gameweeks')
        if payback and payback <= 2:
            explanation.append(f"✓ Quick payback ({payback} GWs to recover hit)")
        elif payback and payback <= 4:
            explanation.append(f"• Reasonable payback ({payback} GWs)")

        # Decision
        explanation.append(f"\n--- RECOMMENDATION ---")
        if transfer_value['total_value'] > 4 and confidence >= 0.7:
            explanation.append(f"✅ STRONGLY RECOMMEND (Worth a hit if needed)")
        elif transfer_value['total_value'] > 2:
            explanation.append(f"✅ RECOMMEND (Good value)")
        elif transfer_value['total_value'] > 0:
            explanation.append(f"⚠️  MARGINAL (Use free transfer only)")
        else:
            explanation.append(f"❌ NOT RECOMMENDED (Negative value)")

        explanation.append(f"{'=' * 70}\n")

        return "\n".join(explanation)

    def explain_captain_choice(
        self,
        captain: Player,
        alternatives: List[Tuple[Player, float]],
        reasoning: Dict
    ) -> str:
        """
        Explain captain choice.

        Args:
            captain: Recommended captain
            alternatives: [(player, expected_points)]
            reasoning: Dict with reasoning factors

        Returns:
            Formatted explanation
        """
        explanation = []
        explanation.append(f"\n{'=' * 70}")
        explanation.append(f"CAPTAIN RECOMMENDATION")
        explanation.append(f"{'=' * 70}")

        explanation.append(f"\n🎖️  Captain: {captain.name} ({captain.position}, £{captain.price}m)")

        if 'expected_points' in reasoning:
            explanation.append(f"   Expected Points: {reasoning['expected_points']:.1f} pts (as captain)")

        # Reasoning
        explanation.append(f"\n--- WHY {captain.name.upper()}? ---")

        if reasoning.get('has_double_gw'):
            explanation.append(f"✓ DOUBLE GAMEWEEK - plays twice!")

        if reasoning.get('fixture_quality', 0) > 1.15:
            explanation.append(f"✓ Excellent fixture (difficulty rating: {reasoning['fixture_quality']:.2f})")
        elif reasoning.get('fixture_quality', 0) > 1.0:
            explanation.append(f"• Good fixture (difficulty rating: {reasoning['fixture_quality']:.2f})")

        if reasoning.get('form') and reasoning['form'] > 6:
            explanation.append(f"✓ Excellent recent form ({reasoning['form']:.1f})")

        if reasoning.get('ownership') and reasoning['ownership'] > 50:
            explanation.append(f"⚠️  Very high ownership ({reasoning['ownership']:.1f}%) - template pick")
        elif reasoning.get('ownership') and reasoning['ownership'] < 20:
            explanation.append(f"🎯 Differential captain ({reasoning['ownership']:.1f}% ownership)")

        # Alternatives
        if alternatives:
            explanation.append(f"\n--- ALTERNATIVES ---")
            for i, (alt, pts) in enumerate(alternatives[:3], 1):
                explanation.append(f"{i}. {alt.name}: {pts:.1f} pts expected")

        explanation.append(f"{'=' * 70}\n")

        return "\n".join(explanation)

    def explain_chip_timing(
        self,
        chip_name: str,
        recommended_gw: int,
        value: float,
        reasoning: Dict
    ) -> str:
        """
        Explain chip timing recommendation.

        Args:
            chip_name: Name of chip
            recommended_gw: Recommended gameweek
            value: Expected value
            reasoning: Reasoning dict

        Returns:
            Formatted explanation
        """
        explanation = []
        explanation.append(f"\n{'=' * 70}")
        explanation.append(f"{chip_name.upper()} RECOMMENDATION")
        explanation.append(f"{'=' * 70}")

        explanation.append(f"\nRecommended: GW{recommended_gw}")
        explanation.append(f"Expected Value: +{value:.1f} pts")

        explanation.append(f"\n--- WHY GW{recommended_gw}? ---")

        if chip_name == 'wildcard':
            if reasoning.get('dgw_bonus', 0) > 0:
                explanation.append(f"✓ Positions you for upcoming Double Gameweek")
            if reasoning.get('squad_health', 1) < 0.7:
                explanation.append(f"✓ Squad needs refresh (health: {reasoning.get('squad_health', 0):.0%})")
            if reasoning.get('transfers_needed', 0) >= 5:
                explanation.append(f"✓ Many transfers needed ({reasoning['transfers_needed']})")

        elif chip_name == 'bench_boost':
            if reasoning.get('dgw_count', 0) >= 8:
                explanation.append(f"✓ {reasoning['dgw_count']} players in Double Gameweek!")
            if reasoning.get('bench_quality', 0) > 15:
                explanation.append(f"✓ Strong bench (expected: {reasoning['bench_quality']:.1f} pts)")

        elif chip_name == 'triple_captain':
            if reasoning.get('has_dgw'):
                explanation.append(f"✓ Captain has Double Gameweek")
            if reasoning.get('captain_pts', 0) > 15:
                explanation.append(f"✓ High captain potential ({reasoning['captain_pts']:.1f} pts expected)")

        elif chip_name == 'free_hit':
            if reasoning.get('blank_count', 0) >= 5:
                explanation.append(f"✓ {reasoning['blank_count']} players have blank gameweek")
            if reasoning.get('opportunity', 0) > 25:
                explanation.append(f"✓ Large opportunity ({reasoning['opportunity']:.1f} pts gain)")

        explanation.append(f"{'=' * 70}\n")

        return "\n".join(explanation)

    def explain_long_term_plan(
        self,
        plan: Dict,
        horizon: int = 5
    ) -> str:
        """
        Explain long-term optimization plan.

        Args:
            plan: Season plan dict
            horizon: Gameweeks to explain

        Returns:
            Formatted explanation
        """
        explanation = []
        explanation.append(f"\n{'=' * 70}")
        explanation.append(f"LONG-TERM PLAN (Next {horizon} Gameweeks)")
        explanation.append(f"{'=' * 70}")

        explanation.append(f"\n🎯 Strategy: Planning for cumulative season rewards")
        explanation.append(f"   Not just optimizing next GW, but GW → GW38")

        # Transfer plan
        if 'transfers' in plan:
            explanation.append(f"\n--- TRANSFER SEQUENCE ---")
            for gw, transfer_info in plan['transfers'].items():
                if gw <= plan.get('current_gw', 0) + horizon:
                    explanation.append(f"\nGW{gw}:")
                    for t in transfer_info:
                        explanation.append(f"  • {t['out']} → {t['in']} ({t['reason']})")

        # Chip timing
        if 'chips' in plan:
            explanation.append(f"\n--- CHIP TIMING ---")
            for gw, chip in plan['chips'].items():
                if gw <= plan.get('current_gw', 0) + horizon:
                    explanation.append(f"GW{gw}: {chip['name']} ({chip['reason']})")

        # Key insights
        explanation.append(f"\n--- KEY INSIGHTS ---")
        if 'insights' in plan:
            for insight in plan['insights']:
                explanation.append(f"• {insight}")
        else:
            explanation.append(f"• Transfer sequencing optimizes fixture swings")
            explanation.append(f"• Chip timing coordinated globally")
            explanation.append(f"• Building towards optimal end-of-season squad")

        explanation.append(f"{'=' * 70}\n")

        return "\n".join(explanation)


class ProgressBar:
    """Simple progress bar for terminal output."""

    @staticmethod
    def print_bar(current: int, total: int, prefix: str = "", length: int = 40):
        """Print a progress bar."""
        filled = int(length * current / total)
        bar = '█' * filled + '░' * (length - filled)
        percent = f"{100 * current / total:.1f}%"
        print(f"\r{prefix} |{bar}| {percent} ({current}/{total})", end='', flush=True)
        if current == total:
            print()  # New line on completion


def format_summary_table(
    headers: List[str],
    rows: List[List[any]],
    title: Optional[str] = None
) -> str:
    """
    Format data as ASCII table.

    Args:
        headers: Column headers
        rows: Data rows
        title: Optional table title

    Returns:
        Formatted table string
    """
    # Calculate column widths
    col_widths = [len(h) for h in headers]
    for row in rows:
        for i, cell in enumerate(row):
            col_widths[i] = max(col_widths[i], len(str(cell)))

    # Build table
    lines = []

    if title:
        total_width = sum(col_widths) + 3 * (len(headers) - 1)
        lines.append(f"\n{title}")
        lines.append("=" * total_width)

    # Header
    header_line = " | ".join(h.ljust(w) for h, w in zip(headers, col_widths))
    lines.append(header_line)
    lines.append("-" * len(header_line))

    # Rows
    for row in rows:
        row_line = " | ".join(str(cell).ljust(w) for cell, w in zip(row, col_widths))
        lines.append(row_line)

    return "\n".join(lines)
