"""Central configuration. Every value can be overridden with an environment variable."""
import os
from pathlib import Path

# MLflow 3+ refuses the plain-file tracking store unless this is set,
# so it must be in the environment before mlflow is imported anywhere.
os.environ.setdefault("MLFLOW_ALLOW_FILE_STORE", "true")
os.environ.setdefault("MLFLOW_DISABLE_AGENT_HINT", "1")

BASE_DIR = Path(__file__).resolve().parent.parent

# Web server
HOST = os.environ.get("HOST", "127.0.0.1")
PORT = int(os.environ.get("PORT", 5005))
DEBUG = os.environ.get("FLASK_DEBUG", "1") == "1"

# MLflow
MLFLOW_TRACKING_URI = os.environ.get("MLFLOW_TRACKING_URI", (BASE_DIR / "mlruns").as_uri())
MLFLOW_EXPERIMENT = os.environ.get("MLFLOW_EXPERIMENT", "stock-price-prediction")

# Modelling
DEFAULT_YEARS = 1
ALLOWED_YEARS = (1, 2, 5)
TEST_SIZE = 0.2
MIN_TRADING_DAYS = 30

# Scheduler
SCHEDULE_TIME = os.environ.get("SCHEDULE_TIME", "12:00")
SCHEDULE_SYMBOLS = [s.strip().upper() for s in os.environ.get("SCHEDULE_SYMBOLS", "AAPL").split(",") if s.strip()]

# Quick-pick tickers shown on the home page
POPULAR_TICKERS = ("AAPL", "MSFT", "NVDA", "TSLA", "AMZN", "GOOGL", "META")

# Day Trader skills (vendored from github.com/Jakeschincariol/day-trader-skill)
SKILLS_DIR = BASE_DIR / "vendor" / "day_trader_skill"
# Each mode gets its own working folder; the skills share files in its trader/ subfolder.
TRADER_WORKSPACE = Path(os.environ.get("TRADER_WORKSPACE", BASE_DIR / "trader_workspace"))
TRADER_MAX_RUN_SECONDS = int(os.environ.get("TRADER_MAX_RUN_SECONDS", 30 * 60))
