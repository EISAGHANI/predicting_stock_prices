"""Day Trader page and its JSON API."""
import json

from flask import Blueprint, Response, jsonify, render_template, request

from . import catalog, runner

bp = Blueprint("trader", __name__, url_prefix="/trader")


def _body() -> dict:
    # JSON only: a cross-site form post cannot send it without a CORS preflight.
    return request.get_json(force=False, silent=False) or {}


@bp.errorhandler(runner.InputError)
def _bad_input(exc):
    return jsonify(error=str(exc)), 400


@bp.errorhandler(runner.Busy)
def _busy(exc):
    return jsonify(error=str(exc)), 409


@bp.get("/")
def page():
    return render_template("trader.html", catalog=catalog.to_json(), demo_day=catalog.DEMO_DAY_LABEL)


@bp.get("/api/state")
def state():
    return jsonify(runner.state(request.args.get("mode", "demo")))


@bp.get("/api/clock")
def clock():
    return jsonify(runner.market_clock())


@bp.get("/api/file")
def file():
    return jsonify(runner.read_file(request.args.get("mode", "demo"), request.args.get("path", "")))


@bp.post("/api/settings")
def settings():
    body = _body()
    return jsonify(runner.write_settings(body.get("mode", ""), body.get("values") or {}))


@bp.post("/api/reset")
def reset():
    runner.reset(_body().get("mode", ""))
    return jsonify(ok=True)


@bp.post("/api/cancel")
def cancel():
    return jsonify(cancelled=runner.cancel(_body().get("mode", "")))


@bp.post("/api/run")
def run():
    body = _body()
    events = runner.start(body.get("skill", ""), body.get("action", ""), body.get("values") or {}, body.get("mode", ""))
    lines = (json.dumps(e) + "\n" for e in events)
    return Response(lines, mimetype="application/x-ndjson",
                    headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})
