"""
backend/ai/forecasting/holt_winters.py
────────────────────────────────────────
Holt-Winters Exponential Smoothing — genuine statistical forecasting.

Why Holt-Winters:
  - Handles both trend AND seasonality (restaurant data has both)
  - Runs in pure Python — no scipy, no numpy required
  - Produces real confidence intervals based on forecast error variance
  - Appropriate for 30-90 days of daily revenue data

Replaces the extrapolation in revenue_forecaster.py:
  Old: avg_daily * day_of_week_multiplier  (this is not forecasting)
  New: Holt-Winters with weekly seasonality + confidence intervals

The model uses:
  - Alpha (α): level smoothing — how fast the level adapts (0.3)
  - Beta  (β): trend smoothing — how fast the trend adapts (0.1)
  - Gamma (γ): seasonal smoothing — how fast seasons adapt (0.2)
  - Season length (m): 7 (weekly seasonality for restaurants)

Reference: Hyndman & Athanasopoulos, "Forecasting: Principles and Practice"
"""

import math
from datetime import date, timedelta
from typing import NamedTuple


class HWForecast(NamedTuple):
    date:          str
    day:           str
    predicted:     float
    ci_low:        float
    ci_high:       float
    ci_width_pct:  float   # Width of CI as % of predicted (smaller = more confident)


class HoltWintersResult(NamedTuple):
    forecasts:       list[HWForecast]
    model_mse:       float   # Mean Squared Error on training data (model fit quality)
    model_mae_pct:   float   # Mean Absolute Error as % of mean (interpretable accuracy)
    trend_direction: str     # "up", "down", "flat"
    trend_pct_week:  float   # % change per week implied by the trend component


def forecast(
    daily_values: list[float],      # Ordered time series (oldest first)
    daily_dates:  list[date],       # Corresponding dates
    horizon:      int = 7,          # Days to forecast
    alpha:        float = 0.3,      # Level smoothing
    beta:         float = 0.1,      # Trend smoothing
    gamma:        float = 0.2,      # Seasonal smoothing
) -> HoltWintersResult:
    """
    Fit Holt-Winters additive model and produce a multi-day forecast.

    Minimum data requirement: 2 full seasonal periods (14 days).
    Falls back to simple moving average if insufficient data.
    """
    m = 7  # Weekly seasonality

    if len(daily_values) < 2 * m:
        return _fallback_forecast(daily_values, daily_dates, horizon)

    # ── Initialisation (Hyndman method) ──────────────────────────────────────
    n = len(daily_values)

    # Level: average of first season
    level = sum(daily_values[:m]) / m

    # Trend: average of (second season avg - first season avg) / m
    if n >= 2 * m:
        trend = (sum(daily_values[m:2*m]) - sum(daily_values[:m])) / (m * m)
    else:
        trend = 0.0

    # Seasonal indices: initial value = actual - level, normalised to sum to 0
    seasonal = []
    for i in range(m):
        avg = sum(daily_values[i::m]) / len(daily_values[i::m])
        seasonal.append(avg - level)

    # Normalise: seasonal components should sum to 0 over a full period
    seasonal_mean = sum(seasonal) / m
    seasonal = [s - seasonal_mean for s in seasonal]

    # ── Training pass ─────────────────────────────────────────────────────────
    errors = []
    for t in range(n):
        s_idx   = t % m
        y_hat   = level + trend + seasonal[s_idx]
        error   = daily_values[t] - y_hat
        errors.append(error)

        # Update components
        new_level    = alpha * (daily_values[t] - seasonal[s_idx]) + (1 - alpha) * (level + trend)
        new_trend    = beta  * (new_level - level) + (1 - beta) * trend
        new_seasonal = gamma * (daily_values[t] - new_level) + (1 - gamma) * seasonal[s_idx]

        level    = new_level
        trend    = new_trend
        seasonal[s_idx] = new_seasonal

    # ── Error statistics ──────────────────────────────────────────────────────
    # Use last half of training data (model has warmed up by then)
    recent_errors = errors[n // 2:]
    mse   = sum(e ** 2 for e in recent_errors) / max(len(recent_errors), 1)
    rmse  = math.sqrt(mse)
    mean_val = sum(daily_values) / len(daily_values)
    mae_pct  = (sum(abs(e) for e in recent_errors) / max(len(recent_errors), 1)) / max(mean_val, 1) * 100

    # ── Forecast ──────────────────────────────────────────────────────────────
    last_date = daily_dates[-1]
    forecasts = []

    for h in range(1, horizon + 1):
        s_idx    = (n + h - 1) % m
        y_hat    = level + h * trend + seasonal[s_idx]
        y_hat    = max(0.0, y_hat)   # Revenue can't be negative

        # CI: grows with forecast horizon (h steps of variance accumulation)
        # 95% CI ≈ ±1.96 * RMSE * sqrt(h) for additive model
        ci_half  = 1.96 * rmse * math.sqrt(h)
        ci_low   = max(0.0, y_hat - ci_half)
        ci_high  = y_hat + ci_half
        ci_width_pct = (ci_high - ci_low) / max(y_hat, 1) * 100

        future_date = last_date + timedelta(days=h)
        forecasts.append(HWForecast(
            date         = future_date.isoformat(),
            day          = future_date.strftime("%A"),
            predicted    = round(y_hat, 2),
            ci_low       = round(ci_low, 2),
            ci_high      = round(ci_high, 2),
            ci_width_pct = round(ci_width_pct, 1),
        ))

    # ── Trend summary ─────────────────────────────────────────────────────────
    trend_pct_week  = (trend * 7 / max(abs(level), 1)) * 100
    trend_direction = "up" if trend_pct_week > 1 else ("down" if trend_pct_week < -1 else "flat")

    return HoltWintersResult(
        forecasts       = forecasts,
        model_mse       = round(mse, 2),
        model_mae_pct   = round(mae_pct, 1),
        trend_direction = trend_direction,
        trend_pct_week  = round(trend_pct_week, 2),
    )


def _fallback_forecast(
    daily_values: list[float],
    daily_dates:  list[date],
    horizon:      int,
) -> HoltWintersResult:
    """
    Fallback for restaurants with <14 days of data.
    Uses simple mean with wide confidence intervals.
    Honest: labels itself as preliminary, not a statistical forecast.
    """
    mean_val = sum(daily_values) / max(len(daily_values), 1)
    std_dev  = math.sqrt(
        sum((v - mean_val) ** 2 for v in daily_values) / max(len(daily_values), 1)
    )
    last_date = daily_dates[-1] if daily_dates else date.today()
    forecasts = []
    for h in range(1, horizon + 1):
        future_date = last_date + timedelta(days=h)
        forecasts.append(HWForecast(
            date         = future_date.isoformat(),
            day          = future_date.strftime("%A"),
            predicted    = round(mean_val, 2),
            ci_low       = round(max(0, mean_val - 2 * std_dev), 2),
            ci_high      = round(mean_val + 2 * std_dev, 2),
            ci_width_pct = round((4 * std_dev) / max(mean_val, 1) * 100, 1),
        ))
    return HoltWintersResult(
        forecasts       = forecasts,
        model_mse       = std_dev ** 2,
        model_mae_pct   = 999.0,     # Not meaningful yet
        trend_direction = "unknown",
        trend_pct_week  = 0.0,
    )


def to_api_format(result: HoltWintersResult) -> dict:
    """Convert to the dict format expected by the analytics API."""
    return {
        "forecast": [
            {
                "date":            f.date,
                "day":             f.day,
                "predicted_revenue": int(f.predicted),
                "confidence_low":  int(f.ci_low),
                "confidence_high": int(f.ci_high),
                "confidence_width_pct": f.ci_width_pct,
                # Width < 30% = tight CI = high confidence
                "confidence_quality": (
                    "high" if f.ci_width_pct < 30
                    else "medium" if f.ci_width_pct < 60
                    else "low"
                ),
            }
            for f in result.forecasts
        ],
        "model_quality": {
            "mae_pct":          result.model_mae_pct,
            "mse":              result.model_mse,
            "trend_direction":  result.trend_direction,
            "trend_pct_week":   result.trend_pct_week,
            "quality_label":    (
                "good" if result.model_mae_pct <= 10
                else "acceptable" if result.model_mae_pct <= 20
                else "preliminary"
            ),
            "note": (
                "Holt-Winters exponential smoothing with weekly seasonality."
                if result.model_mae_pct < 999
                else "Insufficient history for statistical forecast. Showing mean estimate."
            ),
        },
    }
