"""Run the web app:  python app.py   (then open http://127.0.0.1:5005)"""
import logging

from stock_predictor import config
from stock_predictor.web import create_app

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

app = create_app()

if __name__ == "__main__":
    app.run(host=config.HOST, port=config.PORT, debug=config.DEBUG)
