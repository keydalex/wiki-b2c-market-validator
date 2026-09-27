"""Localization Priority Matrix and Expansion Priority Score (S_i in [0, 100])."""

from typing import Any, Dict, List
import pandas as pd


def compute_localization_matrix(
    candidates: List[Dict[str, Any]],
    weight_volume: float = 0.40,
    weight_velocity: float = 0.40,
    weight_trust: float = 0.20,
) -> List[Dict[str, Any]]:
    """
    Rank candidate languages/markets by composite Expansion Priority Score (S_i).
    
    Formula:
        S_i = w_vol * V_i + w_vel * G_i + w_trust * T_i
        
    Quadrants:
        - High-Growth Star (S_i >= 70, T_i >= 65): Immediate priority 1 expansion.
        - Hype Trap (G_i >= 65, T_i < 50): High velocity driven by hype; test with light MVP.
        - Steady Evergreen Niche (V_i >= 50, T_i >= 70, G_i in [30..60]): Low risk stable expansion.
        - Declining / Low Demand (S_i < 40): Do not invest.
        
    Args:
        candidates: List of dicts with:
            'lang': language code ('pl', 'cs', 'uk', etc.)
            'views': total filtered views
            'growth_pct': CAGR or robust growth %
            'trust_score': Trust Score (0..100)
            'article_title': Canonical article title
            
    Returns:
        Sorted list of candidate dicts with calculated indices, ranks, and founder recommendation.
    """
    if not candidates:
        return []

    df = pd.DataFrame(candidates)

    # 1. Normalize Volume Index V_i (0 to 100)
    max_views = df["views"].max() if df["views"].max() > 0 else 1.0
    min_views = df["views"].min()
    if max_views > min_views:
        df["volume_index"] = ((df["views"] - min_views) / (max_views - min_views)) * 100.0
    else:
        df["volume_index"] = 50.0

    # 2. Normalize Velocity Index G_i (0 to 100)
    # Clip extreme negative/positive growth for fair scaling
    clipped_growth = df["growth_pct"].clip(lower=-50.0, upper=150.0)
    max_growth = clipped_growth.max()
    min_growth = clipped_growth.min()
    if max_growth > min_growth:
        df["velocity_index"] = ((clipped_growth - min_growth) / (max_growth - min_growth)) * 100.0
    else:
        df["velocity_index"] = 50.0

    # 3. Trust Index T_i (already 0 to 100)
    df["trust_index"] = df["trust_score"].clip(lower=0.0, upper=100.0)

    # 4. Composite Priority Score S_i
    df["priority_score"] = (
        weight_volume * df["volume_index"]
        + weight_velocity * df["velocity_index"]
        + weight_trust * df["trust_index"]
    ).round(1)

    # 5. Classify Quadrant
    def classify(row):
        score = row["priority_score"]
        trust = row["trust_index"]
        velocity = row["velocity_index"]
        volume = row["volume_index"]

        if score >= 65.0 and trust >= 60.0:
            return "High-Growth Star (Priority 1: GO)", "Strong volume and clean momentum. Launch localization."
        elif velocity >= 60.0 and trust < 50.0:
            return "Hype Trap (CAUTION)", "Fast growth but low trust (news spikes/bots). Validate with landing page test."
        elif volume >= 50.0 and trust >= 65.0 and velocity >= 25.0:
            return "Steady Evergreen Niche (Priority 2)", "Reliable base audience with stable demand. Low risk."
        elif score < 40.0:
            return "Declining / Underperforming (NO-GO)", "Insufficient volume or negative momentum. Avoid investment."
        else:
            return "Emerging Prospect (Priority 3: Monitor)", "Moderate potential. Observe for 1-2 quarters."

    quadrants = [classify(r)[0] for _, r in df.iterrows()]
    recommendations = [classify(r)[1] for _, r in df.iterrows()]

    df["quadrant"] = quadrants
    df["action_recommendation"] = recommendations

    # Sort descending by priority_score
    df = df.sort_values("priority_score", ascending=False).reset_index(drop=True)
    df["rank"] = df.index + 1

    return df.to_dict(orient="records")
