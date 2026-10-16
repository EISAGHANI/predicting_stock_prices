"""Serialise a PredictionResult into chart data rendered client-side with Plotly.js.

Styling (colours, fonts, theme) lives in static/js/chart.js so the chart follows
the page's light/dark theme.
"""
from .pipeline import PredictionResult


def _dates(index) -> list[str]:
    return [d.strftime("%Y-%m-%d") for d in index]


def chart_payload(result: PredictionResult) -> dict:
    return {
        "symbol": result.symbol,
        "history": {"x": _dates(result.history.index), "y": [round(float(v), 4) for v in result.history]},
        "fit": {"x": _dates(result.test_dates), "y": [round(float(v), 4) for v in result.test_predictions]},
        "forecast": {
            "x": [result.last_date.strftime("%Y-%m-%d"), result.forecast_date.strftime("%Y-%m-%d")],
            "y": [round(result.last_close, 4), round(result.predicted_close, 4)],
        },
    }


def recent_rows(result: PredictionResult, n: int = 10) -> list[dict]:
    """Last `n` closes (newest first) with the day-over-day change, for the table view."""
    recent = result.history.iloc[-(n + 1):]
    pct = recent.pct_change() * 100
    rows = [{"date": d, "close": float(c), "change_pct": float(p)}
            for d, c, p in zip(recent.index, recent, pct)][1:]
    return list(reversed(rows))
