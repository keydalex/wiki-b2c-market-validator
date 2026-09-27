"""Robust non-parametric trend estimation using Theil-Sen estimator and CAGR."""

from typing import Dict, Tuple, Union
import numpy as np
from scipy import stats


def calculate_robust_trend(
    y: Union[np.ndarray, list],
    x: Union[np.ndarray, list] = None,
    alpha: float = 0.95,
) -> Dict[str, Union[float, str]]:
    """
    Compute non-parametric Theil-Sen slope and annualized momentum.
    
    With a breakdown point of ~29%, Theil-Sen is immune to severe temporary traffic spikes
    that would severely distort standard Ordinary Least Squares (OLS) regression.
    
    Formula:
        beta_TS = Median({ (y_j - y_i) / (x_j - x_i) | 1 <= i < j <= n })
        
    Args:
        y: Cleaned daily pageview series
        x: Optional day indices (defaults to 0, 1, ..., n-1)
        alpha: Confidence level for slope interval (default 0.95)
        
    Returns:
        Dictionary with:
            slope (daily delta),
            annualized_slope (views/year),
            start_fitted, end_fitted,
            robust_growth_pct (total growth over period),
            cagr (annualized compound growth rate %),
            ols_slope, ols_r2 (for sensitivity comparison),
            trend_direction
    """
    y_arr = np.asarray(y, dtype=float)
    n = len(y_arr)

    if n < 2:
        return {
            "slope": 0.0,
            "annualized_slope": 0.0,
            "robust_growth_pct": 0.0,
            "cagr": 0.0,
            "r_squared": 0.0,
            "trend_direction": "Undefined (insufficient data)",
        }

    if x is None:
        x_arr = np.arange(n, dtype=float)
    else:
        x_arr = np.asarray(x, dtype=float)

    # 1. Theil-Sen estimator from SciPy
    res = stats.theilslopes(y_arr, x_arr, alpha=alpha)
    slope = float(res.slope)
    intercept = float(res.intercept)
    low_slope = float(res.low_slope)
    high_slope = float(res.high_slope)

    # 2. Fitted values at start and end
    start_fitted = max(1.0, intercept + slope * x_arr[0])
    end_fitted = max(1.0, intercept + slope * x_arr[-1])

    # 3. Robust growth percentage over the entire observation window
    total_delta = end_fitted - start_fitted
    robust_growth_pct = round((total_delta / start_fitted) * 100.0, 2)

    # 4. CAGR (Compound Annual Growth Rate)
    years = (x_arr[-1] - x_arr[0]) / 365.25
    if years >= 0.25 and start_fitted > 0:
        cagr = round(((end_fitted / start_fitted) ** (1.0 / years) - 1.0) * 100.0, 2)
    else:
        cagr = robust_growth_pct

    # 5. OLS comparison to show distortion from spikes
    ols_res = stats.linregress(x_arr, y_arr)
    ols_slope = float(ols_res.slope)
    ols_r2 = float(ols_res.rvalue ** 2)

    # 6. Categorization
    if cagr >= 25.0:
        trend_direction = "Rapid Growth (High Momentum)"
    elif cagr >= 8.0:
        trend_direction = "Moderate Growth (Steady Expansion)"
    elif cagr > -8.0:
        trend_direction = "Stable / Plateau (Mature Interest)"
    else:
        trend_direction = "Declining (Waning Consumer Interest)"

    return {
        "slope": round(slope, 4),
        "low_slope_ci": round(low_slope, 4),
        "high_slope_ci": round(high_slope, 4),
        "annualized_slope": round(slope * 365.25, 2),
        "start_fitted": round(start_fitted, 1),
        "end_fitted": round(end_fitted, 1),
        "robust_growth_pct": robust_growth_pct,
        "cagr": cagr,
        "ols_slope": round(ols_slope, 4),
        "ols_r2": round(ols_r2, 4),
        "trend_direction": trend_direction,
    }
