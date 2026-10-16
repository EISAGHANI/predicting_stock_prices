"""End-to-end prediction pipeline shared by the web app and the scheduler."""
from dataclasses import dataclass

import numpy as np
import pandas as pd

from . import config
from .data import chronological_split, fetch_close_prices, make_supervised, normalize_ticker
from .model import load_model, train_and_log


@dataclass
class PredictionResult:
    symbol: str
    years: int
    history: pd.Series            # actual closing prices
    test_dates: pd.DatetimeIndex  # dates of the hold-out period
    test_predictions: np.ndarray  # model output over the hold-out period
    forecast_date: pd.Timestamp
    predicted_close: float
    run_id: str
    metrics: dict[str, float]

    @property
    def last_close(self) -> float:
        return float(self.history.iloc[-1])

    @property
    def last_date(self) -> pd.Timestamp:
        return self.history.index[-1]

    @property
    def change(self) -> float:
        return self.predicted_close - self.last_close

    @property
    def change_pct(self) -> float:
        return self.change / self.last_close * 100

    def summary(self) -> str:
        return (f"{self.symbol}: last close {self.last_close:.2f} ({self.last_date:%Y-%m-%d}) -> "
                f"predicted {self.predicted_close:.2f} for {self.forecast_date:%Y-%m-%d} "
                f"({self.change_pct:+.2f}%), test RMSE {self.metrics['test_rmse']:.2f}, run {self.run_id}")


def run_prediction(raw_symbol: str, years: int = config.DEFAULT_YEARS) -> PredictionResult:
    symbol = normalize_ticker(raw_symbol)
    close = fetch_close_prices(symbol, years)

    X, y, label_dates = make_supervised(close)
    X_train, X_test, y_train, y_test, test_dates = chronological_split(X, y, label_dates)

    trained = train_and_log(symbol, years, X_train, y_train, X_test, y_test)

    # Reload from the MLflow artifact store to prove the logged model is servable.
    model = load_model(trained.model_uri)
    predicted = float(model.predict(np.array([[close.iloc[-1]]]))[0])

    return PredictionResult(
        symbol=symbol,
        years=years,
        history=close,
        test_dates=test_dates,
        test_predictions=model.predict(X_test),
        forecast_date=close.index[-1] + pd.offsets.BDay(1),
        predicted_close=predicted,
        run_id=trained.run_id,
        metrics=trained.metrics,
    )
