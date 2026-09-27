"""Time-series decomposition, viral spike detection, and academic seasonality analysis."""

from typing import Dict, List, Optional, Tuple, Union
import datetime
import numpy as np
import pandas as pd


def decompose_seasonality_and_spikes(
    df: pd.DataFrame,
    date_col: str = "date",
    value_col: str = "views",
    period: int = 7,
    iqr_multiplier: float = 1.5,
) -> Tuple[pd.DataFrame, Dict[str, Union[float, int, bool, str]]]:
    """
    Decompose time series into Trend, Weekly Seasonality, and Remainder.
    Detects viral news spikes via IQR rule on residuals and computes the Academic Seasonality Index (ASI).
    
    Formula:
        y_t = T_t + S_t + R_t
        Spike_t = |R_t - Median(R)| > 1.5 * IQR(R)
        R_spike = Sum(Views_spikes) / Sum(Views_total)
        ASI = Mean(Views_Sep_May) / Mean(Views_Jun_Aug)
        
    Args:
        df: DataFrame with date and view count
        date_col: Name of date column
        value_col: Name of numerical value column
        period: Seasonality cycle (default 7 for weekly)
        iqr_multiplier: Threshold for residual outlier detection (default 1.5)
        
    Returns:
        result_df: DataFrame with ['trend', 'seasonality', 'remainder', 'is_spike']
        metrics: Dictionary containing R_spike, ASI, and seasonality interpretation
    """
    data = df.copy().sort_values(date_col).reset_index(drop=True)
    y = data[value_col].astype(float).values
    n = len(y)

    if n < 14:
        # Too short for weekly decomposition, return trivial decomposition
        data["trend"] = y
        data["seasonality"] = 0.0
        data["remainder"] = 0.0
        data["is_spike"] = False
        return data, {
            "spike_count": 0,
            "spike_ratio": 0.0,
            "spike_traffic_share": 0.0,
            "academic_seasonality_index": 1.0,
            "seasonality_type": "insufficient_data",
        }

    # 1. Trend Estimation via rolling 7-day moving median / average
    # Center rolling window
    trend = pd.Series(y).rolling(window=period, center=True, min_periods=1).median().values

    # 2. Detrended series
    detrended = y - trend

    # 3. Weekly Seasonality: average detrended value by day of week
    dates = pd.to_datetime(data[date_col])
    day_of_week = dates.dt.dayofweek.values
    seasonal_pattern = np.zeros(7)
    for dow in range(7):
        mask = day_of_week == dow
        if np.any(mask):
            seasonal_pattern[dow] = np.median(detrended[mask])
    # Normalize seasonal pattern to sum to 0
    seasonal_pattern -= np.mean(seasonal_pattern)

    seasonality = np.array([seasonal_pattern[dow] for dow in day_of_week])

    # 4. Remainder (Residuals)
    remainder = y - trend - seasonality

    # 5. Viral Spike Detection via IQR on Remainder
    q25 = np.percentile(remainder, 25)
    q75 = np.percentile(remainder, 75)
    iqr = q75 - q25
    med_rem = np.median(remainder)

    # We care especially about positive viral traffic spikes
    upper_spike_threshold = med_rem + iqr_multiplier * max(iqr, 1.0)
    is_spike = remainder > upper_spike_threshold

    data["trend"] = trend
    data["seasonality"] = seasonality
    data["remainder"] = remainder
    data["is_spike"] = is_spike

    spike_count = int(np.sum(is_spike))
    total_views = float(np.sum(y)) if np.sum(y) > 0 else 1.0
    spike_views = float(np.sum(y[is_spike]))
    spike_traffic_share = round(spike_views / total_views, 4)

    # 6. Academic / Annual Seasonality Index (ASI)
    # Months 9,10,11,12,1,2,3,4,5 = Academic year; Months 6,7,8 = Summer break
    months = dates.dt.month.values
    academic_mask = np.isin(months, [9, 10, 11, 12, 1, 2, 3, 4, 5])
    summer_mask = np.isin(months, [6, 7, 8])

    if np.any(academic_mask) and np.any(summer_mask):
        academic_mean = float(np.mean(y[academic_mask]))
        summer_mean = float(np.mean(y[summer_mask]))
        asi = round(academic_mean / (summer_mean + 1e-5), 2)
    else:
        asi = 1.0

    if asi >= 1.35:
        seasonality_type = "Strong Academic / School Cyclical (Demand peaks in school year, dips in summer)"
    elif asi >= 1.15:
        seasonality_type = "Moderate Academic Cyclical"
    elif asi <= 0.85:
        seasonality_type = "Summer / Leisure Seasonal (Demand peaks in summer)"
    else:
        seasonality_type = "Evergreen (Stable year-round demand)"

    metrics = {
        "spike_count": spike_count,
        "spike_ratio": round(spike_count / n, 4),
        "spike_traffic_share": spike_traffic_share,
        "academic_seasonality_index": asi,
        "seasonality_type": seasonality_type,
    }

    return data, metrics
