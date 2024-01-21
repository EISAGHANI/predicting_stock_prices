import os
import mlflow
import pandas as pd
import yfinance as yf

from sklearn.model_selection import train_test_split
from sklearn.metrics import mean_squared_error
from sklearn.linear_model import LinearRegression

from flask import Flask, render_template, request
from plotly.subplots import make_subplots
import plotly.graph_objects as go


app = Flask(__name__)

# Step 1: Fetch Data


def fetch_stock_data(symbol, years_ago):
    end_date = pd.to_datetime('today')
    start_date = end_date - pd.DateOffset(years=years_ago)
    data = yf.download(symbol, start=start_date, end=end_date)
    return data

# Step 2: Preprocess Data


def preprocess_data(data):
    # Assuming you have a 'Close' column in your data
    features = data['Close'].values[:-1].reshape(-1, 1)
    labels = data['Close'].shift(-1).dropna().values

    # Check if the number of samples in features and labels match
    if len(features) != len(labels):
        raise ValueError(
            "Inconsistent number of samples between features and labels.")

    # Split the data into training and testing sets
    X_train, X_test, y_train, y_test = train_test_split(
        features, labels, test_size=0.2, random_state=42)

    # Perform any additional preprocessing as needed

    return X_train, X_test, y_train, y_test


# Step 3: Train Model
def train_model(X_train, y_train):

    with mlflow.start_run():
        # Train a linear regression model
        model = LinearRegression()
        model.fit(X_train, y_train)

        run_id = mlflow.active_run().info.run_id

        # Log metrics
        mlflow.log_param("model", "linear_regression")
        mlflow.log_param("data", "stock_prices")
        mlflow.log_metric("mse", mean_squared_error(
            y_train, model.predict(X_train)))

        # Log the model with the name "model" under the "artifacts" directory
        mlflow.sklearn.log_model(sk_model=model, artifact_path="model")

    return run_id

# Step 4: Predict


def make_predictions(model, X_today):
    # Make predictions for tomorrow
    prediction_tomorrow = model.predict(X_today.reshape(1, -1))

    # Create a DataFrame with predictions
    result_df = pd.DataFrame({"Predicted Tomorrow": prediction_tomorrow})

    return result_df

# Plot Stock Prices and Predictions


def plot_stock_predictions(stock_data, predicted_value):
    fig = make_subplots(specs=[[{"secondary_y": True}]])
    fig.add_trace(go.Scatter(x=stock_data.index,
                  y=stock_data['Close'], mode='lines', name='Stock Price'))
    fig.add_trace(go.Scatter(x=[stock_data.index[-1] + pd.Timedelta(days=1)], y=[
                  predicted_value], mode='markers', marker=dict(color='red'), name='Predicted Price'))
    fig.update_layout(title='Stock Price Prediction',
                      xaxis_title='Date',
                      yaxis_title='Stock Price',
                      yaxis2=dict(title='Predicted Price', overlaying='y', side='right'))
    return fig


@app.route('/', methods=['GET', 'POST'])
def index():
    if request.method == 'POST':
        symbol = request.form['tickerSymbol'].upper()
        interval = request.form['interval']  

        interval_seconds = get_interval_seconds(interval)

        schedule_prediction(symbol, interval_seconds)

        return render_template('index.html')
    else:
        return render_template('index.html')


@app.route('/predict', methods=['POST'])
def predict():
    symbol = request.form['tickerSymbol'].upper()

    years_ago = 1
    stock_data = fetch_stock_data(symbol, years_ago)

    X_train, X_test, y_train, y_test = preprocess_data(stock_data)

    run_id = train_model(X_train, y_train)

    model_path = f"mlruns/0/{run_id}/artifacts/model"
    model = mlflow.sklearn.load_model(model_path)

    X_today = stock_data['Close'].values[-1]

    result_df = make_predictions(model, X_today)
    print(result_df)

    plot = plot_stock_predictions(
        stock_data, result_df.iloc[0]['Predicted Tomorrow'])

    return render_template('plot.html', plot=plot.to_html(full_html=False))


if __name__ == '__main__':
    app.run(debug=True)
