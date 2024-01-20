# mlflow_stock_prediction_script.py
import yfinance as yf
import pandas as pd
from sklearn.model_selection import train_test_split
from sklearn.linear_model import LinearRegression
from sklearn.metrics import mean_squared_error
import mlflow
import mlflow.sklearn
import os
from tensorflow import keras
from tensorflow.keras.optimizers import Adam
from flask import Flask, render_template, request, jsonify
from plotly.subplots import make_subplots
import plotly.graph_objects as go

app = Flask(__name__)

# Step 1: Fetch Data
def fetch_stock_data(symbol, years_ago):
    end_date = pd.to_datetime('today')
    start_date = end_date - pd.DateOffset(years=years_ago)
    data = yf.download(symbol, start=start_date, end=end_date)
    print(data)
    return data

# Step 2: Preprocess Data
def preprocess_data(data):
    features = data['Close'].values[:-1].reshape(-1, 1)
    labels = data['Close'].shift(-1).dropna().values

    # Check if the number of samples in features and labels match
    if len(features) != len(labels):
        raise ValueError("Inconsistent number of samples between features and labels.")

    # Split the data into training and testing sets
    X_train, X_test, y_train, y_test = train_test_split(features, labels, test_size=0.2, random_state=42)

    # Perform any additional preprocessing as needed

    return X_train, X_test, y_train, y_test

# Step 3: Train Model
def train_model(X_train, y_train):

    with mlflow.start_run():
        # Train a linear regression model
        model = keras.models.Sequential()

        # Add an LSTM layer with 64 units, returning sequences, and specifying input shape
        model.add(keras.layers.LSTM(units=64,
                                    return_sequences=True,
                                    input_shape=(X_train.shape[1], 1)))

        # Add another LSTM layer with 64 units
        model.add(keras.layers.LSTM(units=64))

        # Add a Dense layer with 32 units
        model.add(keras.layers.Dense(32))

        # Add a Dropout layer with a dropout rate of 0.5
        model.add(keras.layers.Dropout(0.5))

        # Add a Dense layer with 1 unit (output layer)
        model.add(keras.layers.Dense(1))

        model.compile(optimizer=keras.optimizers.Adam(), loss='mse')

        model.fit(X_train, y_train)

        run_id = mlflow.active_run().info.run_id

        # Log metrics
        mlflow.log_param("model", "tensorflow")
        mlflow.log_param("data", "stock_prices")
        mlflow.log_metric("mse", mean_squared_error(y_train, model.predict(X_train)))

        # Log the model with the name "model" under the "artifacts" directory
        mlflow.tensorflow.log_model(model, artifact_path="model")

    return run_id

# Step 4: Predict
def make_predictions(model, X_today):
    # Make predictions for tomorrow
    prediction_tomorrow = model.predict(X_today.reshape(1, -1))

    # Flatten the predicted array
    prediction_tomorrow_flat = prediction_tomorrow.flatten()

    # Create a DataFrame with predictions
    result_df = pd.DataFrame({"Predicted Tomorrow": prediction_tomorrow_flat})

    return result_df

# Plot Stock Prices and Predictions
def plot_stock_predictions(stock_data, predicted_value):
    fig = make_subplots(specs=[[{"secondary_y": True}]])
    fig.add_trace(go.Scatter(x=stock_data.index, y=stock_data['Close'], mode='lines', name='Stock Price'))
    fig.add_trace(go.Scatter(x=[stock_data.index[-1]], y=[predicted_value], mode='markers', marker=dict(color='red'), name='Predicted Price'))
    fig.update_layout(title='Stock Price Prediction',
                      xaxis_title='Date',
                      yaxis_title='Stock Price',
                      yaxis2=dict(title='Predicted Price', overlaying='y', side='right'))
    return fig

# Flask Routes
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/predict', methods=['POST'])
def predict():
    # Retrieve ticker symbol from the form
    symbol = request.form['tickerSymbol'].upper()
    years_ago = 2

    # Fetch Data
    stock_data = fetch_stock_data(symbol, years_ago)

    # Preprocess Data
    X_train, X_test, y_train, y_test = preprocess_data(stock_data)

    # Train Model with all data until yesterday
    run_id = train_model(X_train, y_train)

    # Load the model from MLflow dynamically
    model_path = f"mlruns/0/{run_id}/artifacts/model"  # Adjust the path accordingly
    model = mlflow.tensorflow.load_model(model_path)

    # Use the last closing price as input for prediction
    X_today = stock_data['Close'].values[-1]

    # Make Predictions
    result_df = make_predictions(model, X_today)

    # Plot Predictions
    plot = plot_stock_predictions(stock_data, result_df.iloc[0]['Predicted Tomorrow'])

    return render_template('plot.html', plot=plot.to_html(full_html=False), symbol=symbol)

if __name__ == '__main__':
    app.run(debug=True)