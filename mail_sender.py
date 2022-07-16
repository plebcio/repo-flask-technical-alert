from flask import Flask
import requests
from flask_mail import Mail, Message
from cs50 import SQL
import time, datetime
import functools
from enum import Enum

# local variables
from env_vars import MY_MAIL, MAIL_PASS, DB_NAME, API_KEY

app = Flask(__name__)
mail = Mail(app)  # instantiate the mail class
db = SQL(DB_NAME)

# configuration of mail
app.config['MAIL_SERVER'] = 'smtp.gmail.com'
app.config['MAIL_PORT'] = 465
app.config['MAIL_USERNAME'] = MY_MAIL
app.config['MAIL_PASSWORD'] = MAIL_PASS
app.config['MAIL_USE_TLS'] = False
app.config['MAIL_USE_SSL'] = True
mail = Mail(app)


class MyError(Enum):
    time_out = 1,
    incorrect_ticker = 2
    premium_endpoint = 3

CACHE_SIZE = 50

"""
TODO MAIL STUFF 
# message object mapped to a particular URL ‘/’
@app.route("/")
def index():
    msg = Message(
        'Hello',
        sender='yourId@gmail.com',
        recipients=['receiver’sid@gmail.com']
    )
    msg.body = 'Hello Flask message sent from Flask-Mail'
    mail.send(msg)
    return 'Sent'
"""


def notify():
    notifications, errors_list = check_orders()
    to_retry = []
    # handling the errors
    for errorType, order_id in errors_list.items():
        # time_out error - maybe try again?
        if errorType == MyError.time_out:
            to_retry.append(order_id)
        if errorType == MyError.incorrect_ticker:
            # TODO send the message to the users that ticker is no longer valid
            # remove from database
            db.execute("DELETE FROM orders WHERE id = :id", id=order_id)
        if errorType == MyError.premium_endpoint:
            # TODO send message that the indicator is no longer available
            # remove from database
            db.execute("DELETE FROM orders WHERE id = :id", id=order_id)

    # notification in the format
    # (user id, order id, val of first indicator, val of second indicator)
    for alert in notifications:
        # get user email
        user_email = db.execute("SELECT email FROM users WHERE id = :user_id", user_id=alert[0])
        # TODO send the message

    # TODO maybe do the reties


def check_orders():
    errors_for_users = {}
    # list of notifications to send out
    # format - tuple (user id, order id, val of first indicator, val of second indicator)
    notifications = []

    orders_list = db.execute("SELECT orders.id, tickers.ticker, orders.user_id, orders.script FROM orders "
                             "JOIN tickers ON orders.ticker_id = tickers.id "
                             "LIMIT 4")

    for entry in orders_list:
        # get first indicator data
        # unpack the entry
        ticker = entry["ticker"]
        indicator_1 = entry["script"]["indicator_1"]
        time_period_1 = entry["script"]["time_period"]
        indicator_duration_1 = entry["script"]["indicator_1_len"]

        # get ticker info
        ans = get_indicator_value(ticker, indicator_1, time_period_1, indicator_duration_1)

        # handle errors
        if isinstance(ans, MyError):
            if ans == MyError.time_out:
                print("---> API TIMED OUT <---")
                print(f"For ticker: {ticker}")
                print(f"At {datetime.datetime.now}")
                continue
            if ans == MyError.premium_endpoint:
                print("ERROR")
                print("A premium endpoint, cant get value")
                errors_for_users[int(entry["user_id"])] = (MyError.premium_endpoint, int(entry["id"]))
                continue
            if ans == MyError.incorrect_ticker:
                # add error and remove ticker
                print("-----> API KEY ERROR<-----")
                print(f"     With ticker {ticker}")
                errors_for_users[int(entry["user_id"])] = (MyError.incorrect_ticker, int(entry["id"]))
                #  remove ticker and its orders from the database - TODO handle latter from the errors list
                continue

        indicator_1_value = ans
        # check what the value will be compared to
        # 1) const value
        if entry["script"]["compare"] == "constant":
            # get the const value
            const_val = float(entry["script"]["constant_value"])
            # check if bigger or smaller
            if entry["script"]["bigger-smaller"] == "bigger":
                if indicator_1_value > const_val:
                    # add to notification list
                    notifications.append((entry["user_id"], entry["id"], indicator_1_value, const_val))
            else:
                # entry["script"]["bigger-smaller"] == "smaller"
                if indicator_1_value < const_val:
                    notifications.append((entry["user_id"], entry["id"], indicator_1_value, const_val))
        # 2) price
        elif entry["script"]["compare"] == "price":

            ticker_price = get_price(ticker)
            # ticker is invalid - should not happen because ticker was called earlier for indicator
            if isinstance(ans, MyError):
                if ans == MyError.time_out:
                    print("---> API TIMED OUT <---")
                    print(f"For ticker: {ticker}")
                    print(f"At {datetime.datetime.now}")
                    continue
                if ans == MyError.incorrect_ticker:
                    # add error and remove ticker
                    print("-----> API KEY ERROR<-----")
                    print(f"     With ticker {ticker}")
                    errors_for_users[int(entry["user_id"])] = (MyError.incorrect_ticker, int(entry["id"]))
                    #  remove ticker and its orders from the database - TODO handle latter from the errors list
                    continue

            # adding the notification
            if entry["script"]["bigger-smaller"] == "bigger":
                if indicator_1_value > ticker_price:
                    # add to notification list
                    notifications.append((entry["user_id"], entry["id"], indicator_1_value, ticker_price))
            else:
                # entry["script"]["bigger-smaller"] == "smaller"
                if indicator_1_value < ticker_price:
                    notifications.append((entry["user_id"], entry["id"], indicator_1_value, ticker_price))

        # 3) second indicator
        elif entry["script"]["compare"] == "second-indicator":
            # get second indicator data
            indicator_2 = entry["script"]["indicator_2"]
            indicator_duration_2 = entry["script"]["indicator_2_len"]

            ans = get_indicator_value(ticker, indicator_2, time_period_1, indicator_duration_2)
            # handle errors
            if isinstance(ans, MyError):
                if ans == MyError.time_out:
                    print("---> API TIMED OUT <---")
                    print(f"For ticker: {ticker}")
                    print(f"At {datetime.datetime.now}")
                    continue
                if ans == MyError.premium_endpoint:
                    print("ERROR")
                    print("A premium endpoint, cant get value")
                    errors_for_users[int(entry["user_id"])] = (MyError.premium_endpoint, int(entry["id"]))
                    continue
                if ans == MyError.incorrect_ticker:
                    # add error and remove ticker
                    print("-----> API KEY ERROR<-----")
                    print(f"     With ticker {ticker}")
                    errors_for_users[int(entry["user_id"])] = (MyError.incorrect_ticker, int(entry["id"]))
                    #  remove ticker and its orders from the database - TODO handle latter from the errors list
                    continue

            # if all went well
            indicator_2_value = ans

            if entry["script"]["bigger-smaller"] == "bigger":
                if indicator_1_value > indicator_2_value:
                    # add to notification list
                    notifications.append((entry["user_id"], entry["id"], indicator_1_value, indicator_2_value))
            else:
                # entry["script"]["bigger-smaller"] == "smaller"
                if indicator_1_value < indicator_2_value:
                    notifications.append((entry["user_id"], entry["id"], indicator_1_value, indicator_2_value))

    return notifications, errors_for_users


# responses are cached to avoid extra api calls
# if error occurs returns MyError Enum, else -> float
@functools.lru_cache(maxsize=CACHE_SIZE)
def get_price(ticker):
    quote_url = f"https://www.alphavantage.co/query?function=GLOBAL_QUOTE&symbol={ticker}&apikey={API_KEY}"
    # get price from api
    api_json = requests.get(quote_url).json()

    # timed out
    retries = 0
    while "NOTE" in api_json or "Note" in api_json:
        # maybe sleep 1 min
        time.sleep(60)
        api_json = requests.get(quote_url).json()
        retries += 1
        if retries == 4:
            print("---> API TIMED OUT <---")
            print(api_json)
            return MyError.time_out

    ticker_json = api_json["Global Quote"]
    if "08. previous close" in ticker_json:
        return float(ticker_json["08. previous close"])
    else:
        print("-----> API KEY ERROR<-----")
        print(f"     With ticker {ticker}")
        # TODO remove this ticker and its orders from the database - handle latter
        return MyError.incorrect_ticker


# returns latest value of indicator
# if error occurs returns MyError Enum, else -> float
@functools.lru_cache(maxsize=CACHE_SIZE)
def get_indicator_value(ticker, indicator, interval, time_period):
    indicator_url = f"https://www.alphavantage.co/query?function={indicator}&symbol={ticker}" \
                   f"&interval={interval.lower()}&time_period={time_period}&series_type=close&apikey" \
                   f"={API_KEY}"
    indicator_1_json = requests.get(indicator_url).json()

    # timed out
    retries = 0
    while "Note" in indicator_1_json or "NOTE" in indicator_1_json:
        # maybe sleep 1 min
        time.sleep(60)
        indicator_1_json = requests.get(indicator_1_json).json()
        retries += 1
        if retries == 4:
            print("---> API TIMED OUT <---")
            print(indicator_1_json)
            return MyError.time_out

    # premium endpoint - indicator unavailable
    if "Information" in indicator_1_json:
        print("ERROR")
        print("A premium endpoint, cant get value")
        return MyError.premium_endpoint

    # get the date of the latest value
    if "Meta Data" not in indicator_1_json:
        return MyError.incorrect_ticker

    latest_value = indicator_1_json["Meta Data"]["3: Last Refreshed"]
    # get the latest value of indicator,
    # looks like {Technical Analysis: "ind_name" : { "date" : { "ind_name" : "val"}}}
    return float(indicator_1_json[f"Technical Analysis: {indicator}"][latest_value][indicator])
