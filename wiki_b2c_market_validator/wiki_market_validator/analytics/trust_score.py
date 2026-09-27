"""Composite Trust & Reliability Score algorithm (TS in [0, 100])."""

from typing import Any, Dict


def calculate_trust_score(
    bot_ratio: float,
    spike_traffic_share: float,
    edits_count: int,
    topic_growth_pct: float,
    macro_wiki_growth_pct: float = 0.0,
    academic_seasonality_index: float = 1.0,
    total_views: int = 1000,
) -> Dict[str, Any]:
    """
    Calculate composite Trust & Reliability Score (0 to 100).
    
    Addresses the founder question: 'How much can this growth trend be trusted?'
    
    Decomposition:
        1. Human vs Bot Integrity (35%): 1 - P_bot
        2. Organic vs Spike Continuity (25%): 1 - R_spike
        3. Community Maintenance (20%): min(1, edits / 20)
        4. Macro Market Share Outperformance (20%): Topic vs Platform growth
        
    Penalties:
        - Severe academic seasonality (ASI > 1.40): -10 pts (cyclical school artifact)
        - Very low volume (total_views < 1500): -10 pts (statistical noise)
    """
    # 1. Human integrity component (0..100)
    p_bot = min(1.0, max(0.0, bot_ratio))
    bot_component = (1.0 - p_bot) * 35.0

    # 2. Organic continuity (0..100)
    r_spike = min(1.0, max(0.0, spike_traffic_share))
    spike_component = (1.0 - r_spike) * 25.0

    # 3. Community curation (0..100)
    edits_norm = min(1.0, max(0.0, edits_count / 20.0))
    edits_component = edits_norm * 20.0

    # 4. Macro platform relative outperformance
    # If topic grew +30% while language wiki grew +10%, outperformance is positive
    rel_growth = topic_growth_pct - macro_wiki_growth_pct
    if rel_growth >= 20.0:
        macro_norm = 1.0
    elif rel_growth >= 0.0:
        macro_norm = 0.75
    elif rel_growth >= -15.0:
        macro_norm = 0.50
    else:
        macro_norm = 0.25
    macro_component = macro_norm * 20.0

    raw_score = bot_component + spike_component + edits_component + macro_component

    # Penalties
    penalties = []
    penalty_points = 0.0

    if academic_seasonality_index >= 1.40:
        penalties.append(
            f"High academic seasonality (ASI={academic_seasonality_index:.2f}): "
            "Traffic spikes during school months and crashes in summer."
        )
        penalty_points += 10.0

    if total_views < 1500:
        penalties.append(f"Low total sample size ({total_views} views): Prone to sampling volatility.")
        penalty_points += 10.0

    final_score = max(5.0, min(100.0, raw_score - penalty_points))
    final_score = round(final_score, 1)

    # Trust Category
    if final_score >= 75.0:
        trust_level = "High Trust"
        recommendation = "Data signal is clean, organic, and reliable for commercial product decisions."
    elif final_score >= 55.0:
        trust_level = "Moderate Trust"
        recommendation = "Solid signal, but account for moderate seasonality or traffic spikes in projections."
    elif final_score >= 40.0:
        trust_level = "Speculative / Low Trust"
        recommendation = "Signal is noisy or driven by short-lived media hype. Validate with a lightweight ad test."
    else:
        trust_level = "Unreliable"
        recommendation = "Severe distortion from bots, news anomalies, or lack of audience. Do not invest capital."

    return {
        "trust_score": final_score,
        "trust_level": trust_level,
        "recommendation": recommendation,
        "sub_scores": {
            "human_integrity_score": round((bot_component / 35.0) * 100.0, 1),
            "organic_continuity_score": round((spike_component / 25.0) * 100.0, 1),
            "community_curation_score": round((edits_component / 20.0) * 100.0, 1),
            "macro_outperformance_score": round((macro_component / 20.0) * 100.0, 1),
        },
        "penalties": penalties,
    }
