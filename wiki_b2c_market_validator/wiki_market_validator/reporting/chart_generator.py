"""Publication-quality 2-panel chart generation using Matplotlib (300 DPI PNG).

Preserves exact 2:1 aspect ratio and uses standard Latin labels to prevent font glyph missing errors.
"""

import os
from typing import Any, Dict, List, Optional
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

LANG_DISPLAY_NAMES = {
    "en": "English",
    "uk": "Ukrainian",
    "pl": "Polish",
    "cs": "Czech",
    "de": "German",
    "es": "Spanish",
    "ja": "Japanese",
    "fr": "French",
    "it": "Italian",
}


def generate_market_validation_chart(
    primary_data: pd.DataFrame,
    topic_name: str,
    output_png_path: str,
    theil_sen_info: Optional[Dict[str, Any]] = None,
    comparison_series: Optional[List[Dict[str, Any]]] = None,
    dpi: int = 300,
) -> str:
    """
    Generate a clean 2-panel chart with legible labels and 2:1 aspect ratio.
    """
    os.makedirs(os.path.dirname(os.path.abspath(output_png_path)), exist_ok=True)

    plt.style.use("seaborn-v0_8-whitegrid" if "seaborn-v0_8-whitegrid" in plt.style.available else "default")
    
    # 10 x 5 inches = exact 2:1 ratio
    fig, (ax1, ax2) = plt.subplots(
        2, 1, figsize=(10.0, 5.0), dpi=dpi, gridspec_kw={"height_ratios": [1.25, 0.95]}
    )

    dates = pd.to_datetime(primary_data["date"])
    views = primary_data["views"].values

    if "cleaned_views" in primary_data.columns:
        cleaned = primary_data["cleaned_views"].values
    elif "trend" in primary_data.columns:
        cleaned = primary_data["trend"].values
    else:
        cleaned = views

    # Panel 1: Raw Views + Hampel Cleaned + Theil-Sen Trend + Spike Points
    ax1.plot(dates, views, color="#94a3b8", alpha=0.5, linewidth=0.9, label="Daily Human Views (Raw)")
    ax1.plot(dates, cleaned, color="#2563eb", linewidth=1.8, label="Hampel Baseline (Cleaned Trend)")

    if theil_sen_info and "start_fitted" in theil_sen_info:
        y_trend = np.linspace(theil_sen_info["start_fitted"], theil_sen_info["end_fitted"], len(dates))
        cagr_val = theil_sen_info.get("cagr", 0.0)
        cagr_label = f"Theil-Sen Trendline (CAGR: {cagr_val:+.1f}%)"
        ax1.plot(dates, y_trend, color="#059669", linestyle="--", linewidth=1.8, label=cagr_label)

    if "is_spike" in primary_data.columns:
        spikes = primary_data["is_spike"].values
        if np.any(spikes):
            ax1.scatter(
                dates[spikes],
                views[spikes],
                color="#dc2626",
                s=26,
                zorder=5,
                label=f"Viral Spike / Anomaly (n={int(np.sum(spikes))})",
            )

    ax1.set_title(f"Market Attention & Anomaly Audit: '{topic_name}'", fontsize=10.5, fontweight="bold", pad=5)
    ax1.set_ylabel("Daily Human Views", fontsize=8.5, fontweight="semibold")
    ax1.xaxis.set_major_formatter(mdates.DateFormatter("%b %Y"))
    ax1.tick_params(axis="both", labelsize=8)
    ax1.legend(loc="upper left", frameon=True, fontsize=8, framealpha=0.9)
    ax1.grid(True, linestyle=":", alpha=0.5)

    # Panel 2: Cross-Market Comparison or 7d/30d Moving Averages
    if comparison_series and len(comparison_series) > 0:
        ax2.set_title("Cross-Market Indexed Trajectory (Base Period = 100)", fontsize=9.5, fontweight="bold", pad=5)
        colors = ["#2563eb", "#d97706", "#7c3aed", "#0891b2", "#be185d", "#059669"]

        base_30d = pd.Series(cleaned).rolling(30, min_periods=1).mean().values
        base_init = base_30d[0] if base_30d[0] > 0 else 1.0
        indexed_base = (base_30d / base_init) * 100.0
        ax2.plot(dates, indexed_base, color=colors[0], linewidth=1.8, label=f"{topic_name} (Base=100)")

        for idx, item in enumerate(comparison_series):
            c_df = item["df"].sort_values("date").reset_index(drop=True)
            c_dates = pd.to_datetime(c_df["date"])
            c_views = c_df["views"].values
            c_30d = pd.Series(c_views).rolling(30, min_periods=1).mean().values
            c_init = c_30d[0] if c_30d[0] > 0 else 1.0
            c_indexed = (c_30d / c_init) * 100.0
            color = colors[(idx + 1) % len(colors)]
            label_text = item.get("label", f"Market {idx+1}")
            ax2.plot(c_dates, c_indexed, color=color, linewidth=1.5, label=label_text)

        ax2.set_ylabel("Indexed Score", fontsize=8.5, fontweight="semibold")
        ax2.axhline(100, color="#64748b", linestyle=":", linewidth=0.9)
    else:
        sma_7 = pd.Series(views).rolling(7, min_periods=1).mean()
        sma_30 = pd.Series(views).rolling(30, min_periods=1).mean()
        ax2.set_title("Moving Average Dynamics: 7-Day vs 30-Day Moving Average", fontsize=9.5, fontweight="bold", pad=5)
        ax2.plot(dates, sma_7, color="#d97706", linewidth=1.4, label="7-Day SMA (Fast Momentum)")
        ax2.plot(dates, sma_30, color="#7c3aed", linewidth=1.7, label="30-Day SMA (Macro Baseline)")
        ax2.set_ylabel("Average Views", fontsize=8.5, fontweight="semibold")

    ax2.xaxis.set_major_formatter(mdates.DateFormatter("%b %Y"))
    ax2.tick_params(axis="both", labelsize=8)
    ax2.legend(loc="upper left", frameon=True, fontsize=8, framealpha=0.9)
    ax2.grid(True, linestyle=":", alpha=0.5)

    plt.tight_layout()
    try:
        fig.savefig(output_png_path, dpi=dpi, bbox_inches="tight")
    except PermissionError:
        output_png_path = output_png_path.replace(".png", "_v2.png")
        fig.savefig(output_png_path, dpi=dpi, bbox_inches="tight")
    plt.close(fig)

    return output_png_path
