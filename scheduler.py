"""Run predictions automatically every day.

    python scheduler.py                      # AAPL every day at 12:00
    python scheduler.py MSFT NVDA --at 09:30 # custom symbols and time
    python scheduler.py TSLA --now           # run once immediately and exit
"""
import argparse
import logging
import time

import schedule

from stock_predictor import config
from stock_predictor.data import TickerError
from stock_predictor.pipeline import run_prediction

log = logging.getLogger("scheduler")


def predict_all(symbols: list[str], years: int) -> None:
    for symbol in symbols:
        try:
            log.info(run_prediction(symbol, years).summary())
        except TickerError as exc:
            log.warning(exc)
        except Exception:
            log.exception("Prediction failed for %s", symbol)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("symbols", nargs="*", default=config.SCHEDULE_SYMBOLS, help="ticker symbols")
    parser.add_argument("--at", default=config.SCHEDULE_TIME, help="daily run time, HH:MM (default %(default)s)")
    parser.add_argument("--years", type=int, default=config.DEFAULT_YEARS, choices=config.ALLOWED_YEARS)
    parser.add_argument("--now", action="store_true", help="run once immediately and exit")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    symbols = [s.upper() for s in args.symbols]

    if args.now:
        predict_all(symbols, args.years)
        return

    schedule.every().day.at(args.at).do(predict_all, symbols, args.years)
    log.info("Scheduler running for %s daily at %s. Press Ctrl+C to stop.", ", ".join(symbols), args.at)
    try:
        while True:
            schedule.run_pending()
            time.sleep(1)
    except KeyboardInterrupt:
        log.info("Scheduler stopped.")


if __name__ == "__main__":
    main()
