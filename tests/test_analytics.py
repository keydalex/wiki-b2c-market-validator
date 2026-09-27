"""Unit tests for statistical analytics, Hampel filter, Theil-Sen, STL, and Trust Score."""

import numpy as np
import pandas as pd
import pytest

from wiki_market_validator.analytics.hampel import apply_hampel_filter
from wiki_market_validator.analytics.stl_decomp import decompose_seasonality_and_spikes
from wiki_market_validator.analytics.theil_sen import calculate_robust_trend
from wiki_market_validator.analytics.trust_score import calculate_trust_score
from wiki_market_validator.metrics.localization_matrix import compute_localization_matrix
from wiki_market_validator.metrics.tam_proxy import calculate_tam_proxy


def test_hampel_filter_removes_extreme_spike():
    """Hampel filter must detect and replace extreme single-day spikes without altering trend."""
    np.random.seed(42)
    base = np.linspace(100, 200, 60) + np.random.normal(0, 3, 60)
    # Inject a 1000% viral spike at day 30
    base[30] = 2000.0

    cleaned, outlier_mask, stats = apply_hampel_filter(base, window_half_width=7, n_sigmas=3.0)

    assert outlier_mask[30] is True or outlier_mask[30] == 1
    assert cleaned[30] < 300.0  # Successfully replaced with local median
    assert stats["outlier_count"] >= 1
    assert stats["outlier_ratio"] > 0


def test_theil_sen_robustness_vs_ols():
    """Theil-Sen estimator must maintain positive trend slope despite a massive negative or positive shock."""
    np.random.seed(42)
    # Ground truth: positive slope of +1.0 per day
    x = np.arange(100)
    y = 50.0 + 1.0 * x
    # Inject 5 huge outliers
    y[20:25] = 9999.0

    trend_stats = calculate_robust_trend(y, x)

    # Theil-Sen slope should remain close to 1.0
    assert 0.8 <= trend_stats["slope"] <= 1.2
    # OLS slope is heavily skewed by the outliers
    assert trend_stats["ols_slope"] != trend_stats["slope"]


def test_stl_decomposition_and_asi():
    """STL decomposition should identify weekly seasonality and detect high academic seasonality."""
    dates = pd.date_range("2023-01-01", "2023-12-31")
    # Simulate academic topic: high in Sept-May (months 9-12, 1-5), very low in summer (months 6-8)
    views = []
    for d in dates:
        if d.month in [6, 7, 8]:
            views.append(20 + (d.dayofweek * 2))
        else:
            views.append(100 + (d.dayofweek * 5))

    df = pd.DataFrame({"date": dates, "views": views})
    decomp_df, metrics = decompose_seasonality_and_spikes(df)

    assert metrics["academic_seasonality_index"] > 1.5
    assert "Academic" in metrics["seasonality_type"]
    assert "trend" in decomp_df.columns
    assert "seasonality" in decomp_df.columns


def test_trust_score_penalizes_bots_and_spikes():
    """Trust score should award high points for clean organic data and heavily penalize bots/spikes."""
    # Clean organic signal
    clean_score = calculate_trust_score(
        bot_ratio=0.05,
        spike_traffic_share=0.02,
        edits_count=35,
        topic_growth_pct=25.0,
        macro_wiki_growth_pct=5.0,
        academic_seasonality_index=1.05,
        total_views=50000,
    )
    assert clean_score["trust_score"] >= 80.0
    assert clean_score["trust_level"] == "High Trust"

    # Spam/bot infested or viral spike signal
    spam_score = calculate_trust_score(
        bot_ratio=0.65,
        spike_traffic_share=0.45,
        edits_count=2,
        topic_growth_pct=150.0,
        macro_wiki_growth_pct=0.0,
        academic_seasonality_index=1.1,
        total_views=2000,
    )
    assert spam_score["trust_score"] < 50.0
    assert spam_score["trust_level"] in ["Speculative / Low Trust", "Unreliable"]


def test_tam_proxy_and_localization_matrix():
    """TAM proxy and Localization Matrix calculations should properly scale and rank candidates."""
    tam = calculate_tam_proxy(target_views=50000, benchmark_views=100000, benchmark_market_size_usd=10_000_000.0)
    assert tam["rai"] == 0.5
    assert tam["tam_proxy_usd"] == 4_250_000.0  # 0.5 * 10M * 0.85

    candidates = [
        {"lang": "pl", "article_title": "Post", "views": 80000, "growth_pct": 30.0, "trust_score": 85.0},
        {"lang": "cs", "article_title": "Půst", "views": 25000, "growth_pct": 45.0, "trust_score": 75.0},
        {"lang": "uk", "article_title": "Голодування", "views": 10000, "growth_pct": -5.0, "trust_score": 40.0},
    ]
    ranked = compute_localization_matrix(candidates)

    assert len(ranked) == 3
    assert ranked[0]["lang"] in ["pl", "cs"]
    assert ranked[2]["lang"] == "uk"
    assert "priority_score" in ranked[0]
