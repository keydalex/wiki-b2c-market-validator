"""Total Addressable Market (TAM) Proxy and Relative Attention Index (RAI)."""

from typing import Any, Dict


def calculate_tam_proxy(
    target_views: int,
    benchmark_views: int,
    benchmark_market_size_usd: float = 10_000_000.0,
    conversion_discount: float = 0.85,
) -> Dict[str, Any]:
    """
    Calculate Relative Attention Index (RAI) and estimated TAM Proxy.
    
    Formula:
        RAI = target_views / benchmark_views
        TAM_proxy = RAI * benchmark_market_size_usd * conversion_discount
        
    Args:
        target_views: Filtered human pageviews for target topic
        benchmark_views: Filtered human pageviews for established benchmark topic
        benchmark_market_size_usd: Known annual revenue or market size of benchmark ($)
        conversion_discount: Category-specific willingness-to-pay adjustment factor (default 0.85)
        
    Returns:
        Dictionary with RAI, estimated TAM ($), and relative market share.
    """
    if benchmark_views <= 0:
        return {
            "rai": 1.0,
            "tam_proxy_usd": round(benchmark_market_size_usd, 2),
            "relative_share_pct": 50.0,
            "interpretation": "Benchmark has 0 views; TAM defaulted to benchmark market size.",
        }

    rai = round(target_views / benchmark_views, 4)
    tam_proxy = round(rai * benchmark_market_size_usd * conversion_discount, 2)
    relative_share = round((target_views / (target_views + benchmark_views)) * 100.0, 2)

    if rai >= 1.5:
        category = "Market Dominant (Higher interest than benchmark)"
    elif rai >= 0.75:
        category = "Comparable Scale (Direct competitor size)"
    elif rai >= 0.25:
        category = "Viable Niche (25-75% of benchmark)"
    else:
        category = "Micro Niche (<25% of benchmark)"

    return {
        "rai": rai,
        "tam_proxy_usd": tam_proxy,
        "relative_share_pct": relative_share,
        "market_scale_category": category,
        "target_views": target_views,
        "benchmark_views": benchmark_views,
    }
