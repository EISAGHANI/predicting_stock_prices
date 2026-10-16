"""Fetching market data and turning it into a supervised learning problem."""
import re

import numpy as np
import pandas as pd
import yfinance as yf

from . import config

_TICKER_RE = re.compile(r"^[A-Z0-9.\-^=]{1,15}$")


class TickerError(ValueError):
    """Raised when a ticker is malformed or has no usable price history."""


def normalize_ticker(raw: str) -> str:
    symbol = (raw or "").strip().upper()
    if not _TICKER_RE.match(symbol):
        raise TickerError(f"'{raw}' doesn't look like a valid ticker symbol.")
    return symbol


def fetch_close_prices(symbol: str, years: int) -> pd.Series:
    """Download daily closing prices for the last `years` years."""
    end = pd.Timestamp.today().normalize()
    start = end - pd.DateOffset(years=years)
    data = yf.download(symbol, start=start, end=end, progress=False, auto_adjust=True)

    if data is None or data.empty or "Close" not in data:
        raise TickerError(f"No price data found for '{symbol}'. Check the symbol and try again.")

    close = data["Close"]
    if isinstance(close, pd.DataFrame):  # yfinance returns one column per ticker
        close = close.iloc[:, 0]
    close = close.dropna().rename("Close")

    if len(close) < config.MIN_TRADING_DAYS:
        raise TickerError(f"Not enough trading history for '{symbol}' ({len(close)} days).")
    return close


def make_supervised(close: pd.Series) -> tuple[np.ndarray, np.ndarray, pd.DatetimeIndex]:
    """Feature = close on day t, label = close on day t+1.

    Returns X, y and the dates of the label (the day being predicted).
    """
    X = close.values[:-1].reshape(-1, 1)
    y = close.values[1:]
    return X, y, close.index[1:]


def chronological_split(X, y, dates, test_size: float = config.TEST_SIZE):
    """Hold out the most recent `test_size` fraction - no shuffling for time series."""
    cut = int(len(X) * (1 - test_size))
    return X[:cut], X[cut:], y[:cut], y[cut:], dates[cut:]
