import os
import requests
from flask import redirect, render_template, request, session
from functools import wraps

from time import strptime, mktime

# local variables
from env_vars import API_KEY

# api call setup parameters
alpha_vantage_api_key = API_KEY


def login_required(f):
    """
    Decorate routes to require login.

    https://flask.palletsprojects.com/en/1.1.x/patterns/viewdecorators/
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if session.get("user_id") is None:
            return redirect("/login")
        return f(*args, **kwargs)
    return decorated_function


def indicator_call(ticker, indicator, time_period, length, limit):
    indicator_url = f"https://www.alphavantage.co/query?function={indicator}&symbol={ticker}" \
                    f"&interval={time_period.lower()}&time_period={length}&series_type=close&apikey" \
                    f"={alpha_vantage_api_key}"
    r = requests.get(indicator_url)
    try:
        indicator_data = r.json()[f'Technical Analysis: {indicator}']
    except:
        raise RuntimeError

    indicator_dates = []
    indicator_values = []

    for index, date in zip(range(limit), indicator_data):
        try:
            epoch_time = mktime(strptime(date, "%Y-%m-%d"))
        except:
            epoch_time = mktime(strptime(date, "%Y-%m-%d %H:%M:%S"))
        indicator_dates.insert(0, float(epoch_time)*1000)
        indicator_values.insert(0, float(indicator_data[date][indicator]))

    return indicator_dates, indicator_values


def price_call(ticker, time_period, limit):

    if time_period == "Daily":
        output_size = "&outputsize=full"
        key = 'Time Series (Daily)'

    else:
        output_size = ""
        key = f'{time_period} Time Series'

    print("ticker:" + ticker + "time_period:" + time_period)

    price_url = f"https://www.alphavantage.co/query?function=TIME_SERIES_" \
                f"{time_period.upper()}&symbol={ticker}{output_size}&apikey={alpha_vantage_api_key}"
    r = requests.get(price_url)
    price_data = r.json()[key]

    price_dates = []
    price_values = []

    for index, date in zip(range(limit), price_data):
        try:
            epoch_time = mktime(strptime(date, "%Y-%m-%d"))
        except:
            epoch_time = mktime(strptime(date, "%Y-%m-%d %H:%M:%S"))
        price_dates.insert(0, float(epoch_time)*1000)
        price_values.insert(0, float(price_data[date]['4. close']))

    return price_dates, price_values


