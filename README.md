# Predict stock prices with MLOps
The target is to use historical data to predict the closing price of tomorrow.

## How to use
Best practice is to have some version of conda installed.

### Create a new enviroment

```
conda create -n "mlflow" python=3.12

conda activate mlflow
```

### Install dependencies
```
pip install mlflow

pip install yfinance

pip install pandas

pip install sklearn

pip install flask

pip install plotly
```

### Start it
```
python mlflow_predict_stock_prices.py
```

