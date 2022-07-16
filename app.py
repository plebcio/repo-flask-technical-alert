import os

import psycopg2
import json

import pandas as pd
import datetime as dt
from helpers import login_required, indicator_call, price_call

from cs50 import SQL
from werkzeug.exceptions import default_exceptions, HTTPException, InternalServerError
from werkzeug.security import check_password_hash, generate_password_hash

from flask import Flask, flash, redirect, render_template, request, session, jsonify
from flask_session import Session
# from flask_sqlalchemy import SQLAlchemy

# local variables
from env_vars import DB_NAME


"""
TODO for this file
1) fix the try - except to handle different kinds of errors - depending on message in the api call
    that has to be changed in the helper functions
    ideas:
        instead of raising errors just return tuple (None, [some error message]) and that error message can be rendered
         
2) render a nicer error template


"""

# Configure application
app = Flask(__name__)

# Ensure templates are auto-reloaded
app.config["TEMPLATES_AUTO_RELOAD"] = True


# Ensure responses aren't cached
@app.after_request
def after_request(response):
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Expires"] = 0
    response.headers["Pragma"] = "no-cache"
    return response


# Configure session to use filesystem (instead of signed cookies)
app.config['SESSION_PERMANENT'] = True
app.config['SESSION_TYPE'] = 'filesystem'
app.config['PERMANENT_SESSION_LIFETIME'] = dt.timedelta(minutes=30)
Session(app)

db = SQL(DB_NAME)


@app.route("/index")
@app.route("/")
def index():
    return render_template("index.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        # clear session
        session.clear()
        email = request.form.get("email").strip()
        password = request.form.get("password")
        if not email or not password:
            return render_template("login.html", error="provide an email and a password")
        # check if user in database
        result = db.execute('SELECT id, password FROM users WHERE email=:email', email=email)
        if not result:
            return render_template("login.html", error="No account with such email exists")
        # check password
        if check_password_hash(result[0]['password'], password):
            # update session
            session["user_id"] = result[0]['id']
            flash("Logged In")
            return redirect("/")
        else:
            print("Incorrect email or password")
            return render_template("login.html", error="Incorrect email or password")

    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    flash("logged out successfully")
    return redirect("/")


@app.route("/register", methods=["GET", "POST"])
def register():
    error = None
    if request.method == "POST":
        # get data
        email = request.form.get("email").strip()
        password = request.form.get("password")
        conf_password = request.form.get("confirmation")

        # check for incorrect email
        if email.find('@') == -1:
            return render_template("register.html", error="incorrect email")
        # check if email not in database
        if not db.execute('SELECT * FROM users WHERE email=:email', email=email):

            # error checking
            if password == "" or conf_password == "":
                error = "Input a valid email, password and confirm it"
                return render_template("register.html", error=error)
            if password != conf_password:
                error = "Passwords don't match"
                return render_template("register.html", error=error)
            if password.isalnum():
                error = "Password must contain a special character"
                return render_template("register.html", error=error)

            # add user to database
            password_hash = generate_password_hash(password)
            db.execute("INSERT INTO users(email, password) VALUES(:email, :password)",
                       email=email, password=password_hash)
            return redirect("/login")

        else:
            error = "email already taken"
            return render_template("register.html", error=error)

    # else - method == GET
    return render_template("register.html")


@app.route("/tech", methods=["GET", "POST"])
@login_required
def tech():
    if request.method == "POST":
        LIMIT = 300
        indicator_2 = False
        indicator_2_len = False
        constant_value = False

        # getting the data from the form
        data = {}
        ticker = request.form.get("ticker").strip().upper()
        data['indicator_1'] = request.form.get("indicator_1").strip().upper()
        data['time_period'] = request.form.get("time-period")
        data['indicator_1_len'] = request.form.get("indicator_1_len")
        if not data['indicator_1_len'].isnumeric():
            return render_template("tech.html", error ='Indicator length must be an integer')
        data['bigger-smaller'] = request.form.get("bigger-smaller")
        data['compare'] = request.form.get("compare")

        # extra choices
        x = request.form.get("indicator_2")
        if x:
            data['indicator_2'] = x.strip().upper()
            indicator_2 = True

        x = request.form.get("indicator_2_len")
        if x:
            if not x.isnumeric():
                return render_template("tech.html", error='Indicator length must be an integer')
            data['indicator_2_len'] = x.strip()
            indicator_2_len = True

        x = request.form.get("constant_value")
        if x:
            if not x.isnumeric():
                return render_template("tech.html", error='Constant value must be an integer')
            data['constant_value'] = x.strip()
            constant_value = True

        # check for missing values
        for i in data:
            if not data[i]:
                return render_template("tech.html",
                                       error=f'Error: no {i} was provided, please fill on all available form elements')
        if data["compare"] == "second-indicator":
            if not indicator_2 or not indicator_2_len:
                return render_template("tech.html", error ='Please specify the second indicator and its range')
        elif data["compare"] == "constant_value":
            if not constant_value:
                return render_template("tech.html", error ='Please specify the const value')

        # first call API to see if all worked
        # call indicator to api and return that data to display chart on tech.html
        try:
            indicator_dates, indicator_values = indicator_call(ticker, data['indicator_1'], data['time_period'],
                                                               data['indicator_1_len'], LIMIT)
        except RuntimeError:
            # API call failed
            return render_template("error.html")

        # add the new ticker in none exist
        if len(db.execute("SELECT * FROM tickers WHERE ticker = :ticker", ticker=ticker)) == 0:
            # add ticker to tickers table
            db.execute("INSERT INTO tickers(ticker) VALUES(:ticker)", ticker=ticker)
        # jsonfy the dict and store it as a JSONB in postgresql DB
        json_data = json.dumps(data)
        db.execute("INSERT INTO orders(user_id, ticker_id, script) VALUES(:user_id, (SELECT id FROM tickers"
                   " WHERE ticker = :ticker), :script)", user_id=session["user_id"], ticker=ticker,
                   script=json_data)

        # set which type of data is needed
        # a) constant
        if constant_value:
            return render_template("tech.html", chart=True, mode="constant_value", indicator = data['indicator_1'],
                                   ticker=ticker, indicator_dates=indicator_dates, indicator_values=indicator_values,
                                   constant_value=data['constant_value'], limit=LIMIT)

        # b) second indicator
        if indicator_2:
            # check if indicator call succeeded
            try:
                second_indicator_dates, second_indicator_values = indicator_call(ticker, data['indicator_2'],
                                                                                 data['time_period'],
                                                                                 data['indicator_2_len'], LIMIT)
            except RuntimeError:
                # API call failed
                return render_template("error.html")
            return render_template("tech.html", chart=True, mode="indicator_2", indicator = data['indicator_1'],
                                   ticker = ticker, indicator_dates=indicator_dates,
                                   indicator_values=indicator_values, second_indicator_values = second_indicator_values,
                                   second_indicator=data['indicator_2'], limit=LIMIT)
        # c) price
        else:
            # get the price data
            try:
                price_dates, price_values = price_call(ticker, data['time_period'], LIMIT)
            except KeyError:
                # TODO dont konw if this is the right error
                return render_template("error.html")

            return render_template("tech.html", chart=True, mode="price", indicator = data['indicator_1'],
                                   ticker=ticker, indicator_dates=indicator_dates, indicator_values=indicator_values,
                                   price_values=price_values)

    # method == GET:
    return render_template("tech.html")


@app.route("/test")
def test():
    return render_template("test.html")


