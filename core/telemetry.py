import json
import os
from datetime import datetime

TELEMETRY_FILE = "telemetry.json"
MAX_DAILY_REQUESTS = 1500

def get_today_str():
    return datetime.now().strftime("%Y-%m-%d")

def _load_data():
    if not os.path.exists(TELEMETRY_FILE):
        return {}
    try:
        with open(TELEMETRY_FILE, "r") as f:
            return json.load(f)
    except:
        return {}

def _save_data(data):
    with open(TELEMETRY_FILE, "w") as f:
        json.dump(data, f, indent=2)

def _init_user_today(data, user_str, today):
    if user_str not in data or data[user_str].get("date") != today:
        data[user_str] = {
            "date": today,
            "requests": 0,
            "total_tokens": 0,
            "latency_seconds_sum": 0.0,
            "errors": 0
        }

def log_success(user_id: int, tokens: int, latency: float):
    data = _load_data()
    user_str = str(user_id)
    today = get_today_str()
    
    _init_user_today(data, user_str, today)
    
    data[user_str]["requests"] += 1
    data[user_str]["total_tokens"] += tokens
    data[user_str]["latency_seconds_sum"] += latency
    
    _save_data(data)

def log_error(user_id: int):
    data = _load_data()
    user_str = str(user_id)
    today = get_today_str()
    
    _init_user_today(data, user_str, today)
    data[user_str]["errors"] += 1
    
    _save_data(data)

def get_user_stats(user_id: int):
    data = _load_data()
    user_str = str(user_id)
    today = get_today_str()
    
    if user_str in data and data[user_str].get("date") == today:
        return data[user_str]
    return {
        "date": today,
        "requests": 0,
        "total_tokens": 0,
        "latency_seconds_sum": 0.0,
        "errors": 0
    }
