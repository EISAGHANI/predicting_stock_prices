import schedule
import time
from datetime import datetime, timedelta
from flask import Flask
import requests

app = Flask(__name__)

# Function to trigger the prediction process
def schedule_prediction():
    with app.app_context():
        # Import functions from the main script
        from main_script import fetch_stock_data, preprocess_data, train_model, make_predictions, plot_stock_predictions

        # Ticker symbol for AAPL
        symbol = "AAPL"

        # Fetch stock data
        years_ago = 1
        stock_data = fetch_stock_data(symbol, years_ago)

        # Preprocess data
        X_train, X_test, y_train, y_test = preprocess_data(stock_data)

        # Train the model and get the run_id
        run_id = train_model(X_train, y_train)

        # Load the trained model
        model_path = f"mlruns/0/{run_id}/artifacts/model"
        model = mlflow.sklearn.load_model(model_path)

        # Make predictions
        X_today = stock_data['Close'].values[-1]
        result_df = make_predictions(model, X_today)

        # Print predictions
        print(result_df)



# Schedule the prediction process every day at a specific time (e.g., 12:00 PM)
schedule.every().day.at("12:00").do(schedule_prediction)

# Run the scheduler indefinitely
while True:
    schedule.run_pending()
    time.sleep(1)
