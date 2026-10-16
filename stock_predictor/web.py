"""Flask application: routes and template wiring."""
import logging

from flask import Flask, Response, redirect, render_template, request, url_for
from plotly.offline import get_plotlyjs

from . import config
from .charts import chart_payload, recent_rows
from .data import TickerError
from .pipeline import run_prediction

log = logging.getLogger(__name__)


def create_app() -> Flask:
    app = Flask(
        __name__,
        template_folder=str(config.BASE_DIR / "templates"),
        static_folder=str(config.BASE_DIR / "static"),
    )

    @app.context_processor
    def inject_globals():
        return {
            "popular_tickers": config.POPULAR_TICKERS,
            "allowed_years": config.ALLOWED_YEARS,
            "default_years": config.DEFAULT_YEARS,
        }

    @app.get("/")
    def index():
        return render_template("index.html")

    @app.route("/predict", methods=["GET", "POST"])
    def predict():
        params = request.values
        symbol = params.get("symbol") or params.get("tickerSymbol", "")
        if not symbol:
            return redirect(url_for("index"))

        try:
            years = int(params.get("years", config.DEFAULT_YEARS))
        except ValueError:
            years = config.DEFAULT_YEARS
        if years not in config.ALLOWED_YEARS:
            years = config.DEFAULT_YEARS

        try:
            result = run_prediction(symbol, years)
        except TickerError as exc:
            return render_template("index.html", error=str(exc), symbol=symbol, years=years), 400
        except Exception:
            log.exception("Prediction failed for %s", symbol)
            return render_template(
                "index.html",
                error="Something went wrong while training the model. Please try again.",
                symbol=symbol, years=years,
            ), 500

        log.info(result.summary())
        return render_template(
            "result.html",
            result=result,
            chart=chart_payload(result),
            rows=recent_rows(result),
        )

    @app.get("/vendor/plotly.min.js")
    def plotly_js():
        # Serve the plotly.js bundle shipped with the Python package: no CDN needed.
        resp = Response(get_plotlyjs(), mimetype="application/javascript")
        resp.cache_control.max_age = 60 * 60 * 24 * 7
        return resp

    return app
