"""Model training, evaluation and MLflow logging."""
from dataclasses import dataclass

import mlflow
import mlflow.sklearn
import numpy as np
from sklearn.linear_model import LinearRegression
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score

from . import config

_configured = False


def _setup_mlflow() -> None:
    global _configured
    if not _configured:
        mlflow.set_tracking_uri(config.MLFLOW_TRACKING_URI)
        mlflow.set_experiment(config.MLFLOW_EXPERIMENT)
        _configured = True


@dataclass
class TrainedModel:
    run_id: str
    model_uri: str
    metrics: dict[str, float]


def evaluate(y_true, y_pred) -> dict[str, float]:
    mse = mean_squared_error(y_true, y_pred)
    return {
        "mse": float(mse),
        "rmse": float(np.sqrt(mse)),
        "mae": float(mean_absolute_error(y_true, y_pred)),
        "r2": float(r2_score(y_true, y_pred)),
    }


def train_and_log(symbol: str, years: int, X_train, y_train, X_test, y_test) -> TrainedModel:
    """Fit a linear regression, log params/metrics/model to MLflow."""
    _setup_mlflow()
    with mlflow.start_run(run_name=f"{symbol}-{years}y") as run:
        model = LinearRegression().fit(X_train, y_train)

        metrics = {f"train_{k}": v for k, v in evaluate(y_train, model.predict(X_train)).items()}
        metrics |= {f"test_{k}": v for k, v in evaluate(y_test, model.predict(X_test)).items()}

        mlflow.log_params({
            "model": "linear_regression",
            "symbol": symbol,
            "years": years,
            "train_size": len(X_train),
            "test_size": len(X_test),
        })
        mlflow.log_metrics(metrics)
        info = mlflow.sklearn.log_model(sk_model=model, name="model", input_example=X_train[:1])

    return TrainedModel(run_id=run.info.run_id, model_uri=info.model_uri, metrics=metrics)


def load_model(model_uri: str):
    _setup_mlflow()
    return mlflow.sklearn.load_model(model_uri)
