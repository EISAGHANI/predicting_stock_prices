import os
import schedule
import time
from datetime import datetime, timedelta
import subprocess

def run_mlflow_script():
    script_path = "mlflow_stock_prediction_script.py"  # Replace with the actual path to your script
    python_executable = "python"  # Replace with the path to your Python interpreter (e.g., /usr/bin/python3)
    print(datetime.now())
    subprocess.run([python_executable, script_path])

# Schedule the script to run every day at midnight
#schedule.every().day.at("00:00").do(run_mlflow_script)

# Schedule the script to run every minute
schedule.every().minute.at(":00").do(run_mlflow_script)

while True:
    schedule.run_pending()
    time.sleep(1)
