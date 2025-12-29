import os

from cs50 import SQL
from flask import Flask, flash, redirect, render_template, request, session
from flask_session import Session
from werkzeug.security import check_password_hash, generate_password_hash

from helpers import apology, login_required, lookup, usd

# Configure application
app = Flask(__name__)

# Custom filter
app.jinja_env.filters["usd"] = usd

# Configure session to use filesystem (instead of signed cookies)
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

# Configure CS50 Library to use SQLite database
db = SQL("sqlite:///finance.db")

#DONE
@app.after_request
def after_request(response):
    """Ensure responses aren't cached"""
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Expires"] = 0
    response.headers["Pragma"] = "no-cache"
    return response

#DONE
@app.route("/")
@login_required
def index():
    """Show portfolio of stocks"""

    portfolio=None
    cash_balance=None
    user_id = session["user_id"]

    # Group symbols so user doesn't see "AAPL" multiple times
    # We only want symbols where the user actually owns shares (> 0)
    portfolio = db.execute("""
            SELECT symbol, SUM(shares) as total_shares
            FROM purchaces
            WHERE user_id = ?
            GROUP BY symbol
            HAVING total_shares > 0
        """, user_id)

    cash_balance = db.execute("SELECT cash, username FROM users WHERE id = ?", user_id)
    user_name = cash_balance[0]["username"]
    cash_balance = cash_balance[0]["cash"]
    grand_total=cash_balance # calculate this value in the loop

    for holding in portfolio:
        stock_info = lookup(holding["symbol"])
        # safety check in case lookup fails
        if stock_info:
            holding["stock_name"] = stock_info["name"]
            holding["current_price"] = stock_info["price"]
            holding["holding_value"] = stock_info["price"] * holding["total_shares"]
            grand_total += holding["holding_value"]

    return render_template("index.html", portfolio=portfolio, cash_balance=cash_balance, grand_total=grand_total, user_name=user_name )

#DONE
@app.route("/buy", methods=["GET", "POST"])
@login_required
def buy():
    """Buy shares of stock"""

    # if just visit, then render template
    if request.method == "GET" :
        return render_template("buy.html")
    # if they entered info, then carry out logic for purchace
    else :
        # the following values need to be validated
        symbol = request.form.get("symbol")
        shares = request.form.get("shares")
        stock_info = lookup(symbol) # will return none if something is a miss

        # if symbol wasnt fetched
        if not stock_info :
            return apology('Your requested stock could not be found')

        # Validate Shares (Check if it's a positive integer)
        if not shares or not shares.isdigit() or int(shares) <= 0:
            return apology("Shares must be a positive integer", 400)

        shares = int(shares)
        price = float(stock_info["price"])
        required_balance = price * float(shares)

        # u also need user id, user balance -> fetch using the session??
        user_id = session["user_id"]
        user_balance = db.execute("SELECT cash FROM users WHERE id = ?", user_id)
        user_balance = user_balance[0]["cash"]

        # if insufficient balance
        if required_balance > user_balance:
            return apology('You are broke, insufficient funds for purchase')

        # update the cash of the user
        new_cash = user_balance - required_balance
        db.execute("UPDATE users SET cash= ? WHERE id = ?", new_cash, user_id)

        # insert the purchace record in the purchase table
        db.execute("INSERT INTO purchaces (user_id, symbol, shares, price) VALUES (?, ?, ?, ?)", user_id, symbol.upper(), shares, price)

        # Redirect user to home page
        return redirect("/")

#DONE
@app.route("/history")
@login_required
def history():
    """Show history of transactions"""
    # first check if the user has made any purchces at all
    user_id = session["user_id"]
    user_transaction = db.execute("SELECT symbol,shares,price,timestamp FROM purchaces WHERE user_id = ? ORDER BY timestamp DESC", user_id)
    if user_transaction == [] :
        user_transaction = None
    else :
        for transaction in user_transaction :
            if int(transaction["shares"]) < 0 :
                action = "sell"
            else :
                action = "buy"
            transaction["action"] = action
            transaction["total_value"] = abs(float(transaction["shares"])) * float(transaction["price"])

    return render_template("history.html", user_transaction=user_transaction)

#DONE
@app.route("/login", methods=["GET", "POST"])
def login():
    """Log user in"""

    # Forget any user_id
    session.clear()

    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":
        # Ensure username was submitted
        if not request.form.get("username"):
            return apology("must provide username", 403)

        # Ensure password was submitted
        elif not request.form.get("password"):
            return apology("must provide password", 403)

        # Query database for username
        rows = db.execute(
            "SELECT * FROM users WHERE username = ?", request.form.get("username")
        )

        # Ensure username exists and password is correct
        if len(rows) != 1 or not check_password_hash(
            rows[0]["hash"], request.form.get("password")
        ):
            return apology("invalid username and/or password", 403)

        # Remember which user has logged in
        session["user_id"] = rows[0]["id"]

        # Redirect user to home page
        return redirect("/")

    # User reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("login.html")


#DONE
@app.route("/logout")
def logout():
    """Log user out"""

    # Forget any user_id
    session.clear()

    # Redirect user to login form
    return redirect("/")


#DONE
@app.route("/quote", methods=["GET", "POST"])
@login_required
def quote():
    """Get stock quote."""
    # if theyve just visited, then render form that lets them input stock symbols for look up. render qoute template that allows to submit info
    if request.method == "GET":
        return render_template("quote.html")
    # else, if theyve submitted info via the /qoute route, then render the qouted template that actually shows the look up info
    else:
        symbol = request.form.get("symbol")
        stock_info = lookup(symbol) # will return none if something is a miss
        if not stock_info :
            return apology("Stock Symbol could not be found", 400)

        return render_template("quoted.html", stock_info=stock_info )

#DONE
@app.route("/register", methods=["GET", "POST"])
def register():
    """Register user"""
    # Forget any user_id
    session.clear()

    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")
        confirm_password = request.form.get("confirmation")

        # 1. Check for missing fields
        if not username:
            return apology("must provide username", 400)
        elif not password or not confirm_password:
            return apology("must provide password", 400)

        # 2. Check if passwords match
        if password != confirm_password:
            return apology("passwords do not match", 400)

        # 3. Check if username exists
        rows = db.execute("SELECT * FROM users WHERE username = ?", username)
        if len(rows) > 0:
            return apology("username already exists", 400)

        # 4. Insert and log in
        hash = generate_password_hash(password)
        new_id = db.execute("INSERT INTO users (username, hash) VALUES (?, ?)", username, hash)
        session["user_id"] = new_id
        return redirect("/")

    # If it's a GET request (or no error triggered a return yet), show the form
    return render_template("register.html")

#DONE
@app.route("/sell", methods=["GET", "POST"])
@login_required
def sell():
    """Sell shares of stock"""

    if request.method == "GET" :
        current_holdings = None # this will include stock symbol AND number of respective shares

        #fetch and store the users id
        user_id = session["user_id"]

        # fetch and store all the current shares and the symbols
        current_holdings = db.execute("""
            SELECT symbol, SUM(shares) AS total_shares
            FROM purchaces
            WHERE user_id = ?
            GROUP BY symbol
            HAVING total_shares > 0
        """, user_id)
        return render_template("sell.html", current_holdings=current_holdings)
    else :
        symbol = request.form.get("symbol")
        shares_to_sell = request.form.get("shares")
        user_id = session["user_id"]

        #Basic Validation
        if not symbol:
            return apology("must provide symbol", 400)
        if not shares_to_sell or not shares_to_sell.isdigit() or int(shares_to_sell) <= 0:
            return apology("must provide positive integer of shares", 400)

        shares_to_sell = int(shares_to_sell)

        #Check if user owns enough shares
        rows = db.execute("""
            SELECT SUM(shares) AS total_shares
            FROM purchaces
            WHERE user_id = ? AND symbol = ?
            GROUP BY symbol
        """, user_id, symbol)

        if not rows or rows[0]["total_shares"] < shares_to_sell:
            return apology("not enough shares owned", 400)

        #Get current price and update finances
        stock_info = lookup(symbol)
        price = stock_info["price"] # get the latest price of the stock, api call
        sale_value = price * shares_to_sell

        # Update cash
        db.execute("UPDATE users SET cash = cash + ? WHERE id = ?", sale_value, user_id)

        # Record transaction (negative shares for a sale)
        db.execute("INSERT INTO purchaces (user_id, symbol, shares, price) VALUES (?, ?, ?, ?)",
                   user_id, symbol, -shares_to_sell, price)

        return redirect("/")

#DONE
@app.route("/settings")
@login_required
def settings():
    """Allow user to change account settings"""
    # change password
    # change username
    # add cash
    return render_template("settings.html")

#DONE
@app.route("/changepassword", methods=["GET", "POST"])
@login_required
def changepassword() :
    if request.method == "GET" :
        return render_template("changepassword.html")
    else :
        # 1. Get user data based on SESSION
        user_id = session["user_id"]
        rows = db.execute("SELECT * FROM users WHERE id = ?", user_id)

        # 2. Verify current password
        current_password = request.form.get("password")
        if not current_password or not check_password_hash(rows[0]["hash"], current_password):
            return apology("invalid current password", 403)

        # 3. Get and validate new password
        new_password = request.form.get("new_password")
        confirmation = request.form.get("confirmation")

        if not new_password:
            return apology("must provide new password", 400)

        if new_password != confirmation:
            return apology("passwords do not match", 400)

        # 4. Update the database
        new_hash = generate_password_hash(new_password)
        db.execute("UPDATE users SET hash = ? WHERE id = ?", new_hash, user_id)

        return redirect("/")

@app.route("/changeusername", methods=["GET", "POST"])
@login_required
def changeusername() :
    if request.method == "GET" :
        return render_template("changeusername.html")
    else :
        # 1. Get user data based on SESSION
        user_id = session["user_id"]
        rows = db.execute("SELECT * FROM users WHERE id = ?", user_id)

        # 2. Verify current password
        password = request.form.get("password")
        if not password or not check_password_hash(rows[0]["hash"], password):
            return apology("invalid password", 403)

        # 3. Get and validate new username
        username = request.form.get("username")
        confirmation = request.form.get("confirmation")

        if not username:
            return apology("must provide new username", 400)

        if username != confirmation:
            return apology("usernames do not match", 400)

        # check if username is available
        existing_user = db.execute("SELECT id FROM users WHERE username = ?", username)
        if existing_user:
            return apology("username already taken", 400)

        # 4. Update the database
        db.execute("UPDATE users SET username = ? WHERE id = ?", username, user_id)

        return redirect("/")

@app.route("/addcash", methods=["GET", "POST"])
@login_required
def addcash() :
    if request.method == "GET" :
        return render_template("addcash.html")
    else :
        # Get user data based on SESSION
        user_id = session["user_id"]
        rows = db.execute("SELECT * FROM users WHERE id = ?", user_id)

        # Verify current password
        password = request.form.get("password")
        if not password or not check_password_hash(rows[0]["hash"], password):
            return apology("invalid password", 400)

        # get the cash amount and validate it
        add_cash = -1
        try:
            add_cash = float(request.form.get("cash"))
        except ValueError:
            return apology("amount must be a number", 400)

        if add_cash <= 0:
            return apology("Cash has to be a positive numeric value", 400)

        # now we update the database
        db.execute("UPDATE users SET cash = cash + ? WHERE id = ?", add_cash, user_id)

        return redirect("/")
