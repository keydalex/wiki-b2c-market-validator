"""Hampel filter implementation for robust time-series outlier and spike detection."""

from typing import Dict, List, Tuple, Union
import numpy as np
import pandas as pd


def apply_hampel_filter(
    series: Union[pd.Series, np.ndarray, List[float]],
    window_half_width: int = 7,
    n_sigmas: float = 3.0,
) -> Tuple[np.ndarray, np.ndarray, Dict[str, Union[int, float]]]:
    """
    Robust Hampel filter using local median and Median Absolute Deviation (MAD).
    
    Identifies and replaces isolated spikes/outliers without distorting the underlying trend.
    
    Formula:
        m_t = Median(y_{t-h} ... y_{t+h})
        a_t = Median(|y_{t-h} - m_t| ... |y_{t+h} - m_t|)
        sigma_t = 1.4826 * a_t
        outlier if |y_t - m_t| > n_sigmas * sigma_t
        
    Args:
        series: Daily numerical values (e.g. daily pageviews)
        window_half_width: h (total window size = 2h + 1, default 7 for 15-day window)
        n_sigmas: Outlier threshold multiplier kappa (default 3.0)
        
    Returns:
        cleaned: Array with outliers replaced by local medians
        outlier_mask: Boolean array indicating which indices were outliers
        stats: Summary dictionary with outlier count and ratio
    """
    y = np.asarray(series, dtype=float).copy()
    n = len(y)
    outlier_mask = np.zeros(n, dtype=bool)
    cleaned = y.copy()

    if n < 2 * window_half_width + 1:
        # Series too short for specified window; use global median/MAD fallback
        med = float(np.median(y))
        mad = float(np.median(np.abs(y - med)))
        sigma = 1.4826 * mad
        if sigma > 0:
            outlier_mask = np.abs(y - med) > (n_sigmas * sigma)
            cleaned[outlier_mask] = med
        return cleaned, outlier_mask, {
            "outlier_count": int(np.sum(outlier_mask)),
            "outlier_ratio": float(np.mean(outlier_mask)),
            "window_size": n,
        }

    for i in range(n):
        start = max(0, i - window_half_width)
        end = min(n, i + window_half_width + 1)
        window_vals = y[start:end]

        local_median = float(np.median(window_vals))
        local_mad = float(np.median(np.abs(window_vals - local_median)))
        local_sigma = 1.4826 * local_mad

        # Avoid zero division when local window has identical values
        if local_sigma < 1e-6:
            local_sigma = 1.0

        if np.abs(y[i] - local_median) > (n_sigmas * local_sigma):
            outlier_mask[i] = True
            cleaned[i] = local_median

    outlier_count = int(np.sum(outlier_mask))
    outlier_ratio = float(outlier_count / n) if n > 0 else 0.0

    stats = {
        "outlier_count": outlier_count,
        "outlier_ratio": round(outlier_ratio, 4),
        "window_size": 2 * window_half_width + 1,
        "n_sigmas": n_sigmas,
    }

    return cleaned, outlier_mask, stats
