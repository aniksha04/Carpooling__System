import os
from functools import wraps

from flask import Flask, flash, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash
import mysql.connector
from mysql.connector import Error

app = Flask(__name__,template_folder=".",static_folder="static")
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "change-this-secret-key-for-local-development")


def get_db_connection():
    """Create a fresh MySQL connection for one request/operation."""
    return mysql.connector.connect(
        host=os.environ.get("DB_HOST", "localhost"),
        user=os.environ.get("DB_USER", "root"),
        password=os.environ.get("DB_PASSWORD", "12345678"),
        database=os.environ.get("DB_NAME", "carpool_db"),
        port=int(os.environ.get("DB_PORT", "3306")),
    )


def login_required(view):
    @wraps(view)
    def wrapped_view(*args, **kwargs):
        if "user_id" not in session:
            flash("Please log in first.", "warning")
            return redirect(url_for("login"))
        return view(*args, **kwargs)
    return wrapped_view


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        confirm_password = request.form.get("confirm_password", "")

        if not username or not email or not password:
            flash("Please fill in all required fields.", "danger")
            return render_template("register.html")
        if len(username) > 100 or len(email) > 150:
            flash("Username or email is too long.", "danger")
            return render_template("register.html")
        if len(password) < 8:
            flash("Password must contain at least 8 characters.", "danger")
            return render_template("register.html")
        if password != confirm_password:
            flash("Passwords do not match.", "danger")
            return render_template("register.html")

        conn = None
        cursor = None
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO users (username, email, password_hash) VALUES (%s, %s, %s)",
                (username, email, generate_password_hash(password)),
            )
            conn.commit()
            flash("Registration successful. Please log in.", "success")
            return redirect(url_for("login"))
        except mysql.connector.IntegrityError:
            if conn:
                conn.rollback()
            flash("That username or email is already registered.", "danger")
        except Error as exc:
            if conn:
                conn.rollback()
            app.logger.exception("Registration database error: %s", exc)
            flash("Could not register right now. Check the database settings and tables.", "danger")
        finally:
            if cursor:
                cursor.close()
            if conn and conn.is_connected():
                conn.close()

    return render_template("register.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        if not username or not password:
            flash("Enter your username and password.", "danger")
            return render_template("login.html")

        conn = None
        cursor = None
        try:
            conn = get_db_connection()
            cursor = conn.cursor(dictionary=True)
            cursor.execute(
                "SELECT id, username, password_hash FROM users WHERE username = %s",
                (username,),
            )
            user = cursor.fetchone()
            if user and check_password_hash(user["password_hash"], password):
                session.clear()
                session["user_id"] = user["id"]
                session["username"] = user["username"]
                flash("You are now logged in.", "success")
                return redirect(url_for("dashboard"))
            flash("Incorrect username or password.", "danger")
        except Error as exc:
            app.logger.exception("Login database error: %s", exc)
            flash("Could not log in. Check the database settings and tables.", "danger")
        finally:
            if cursor:
                cursor.close()
            if conn and conn.is_connected():
                conn.close()

    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    flash("You have been logged out.", "success")
    return redirect(url_for("index"))


@app.route("/dashboard")
@login_required
def dashboard():
    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT COUNT(*) AS total FROM rides WHERE seats > 0")
        available_rides = cursor.fetchone()["total"]
        cursor.execute("SELECT COUNT(*) AS total FROM bookings WHERE passenger_id = %s", (session["user_id"],))
        my_bookings = cursor.fetchone()["total"]
        return render_template("dashboard.html", available_rides=available_rides, my_bookings=my_bookings)
    except Error as exc:
        app.logger.exception("Dashboard database error: %s", exc)
        flash("Could not load dashboard data.", "danger")
        return render_template("dashboard.html", available_rides=0, my_bookings=0)
    finally:
        if cursor:
            cursor.close()
        if conn and conn.is_connected():
            conn.close()


@app.route("/rides/offer", methods=["GET", "POST"])
@login_required
def offer_ride():
    if request.method == "POST":
        source = request.form.get("source", "").strip()
        destination = request.form.get("destination", "").strip()
        seats_text = request.form.get("seats", "").strip()

        if not source or not destination or not seats_text:
            flash("Please complete every field.", "danger")
            return render_template("offer_ride.html")
        if source.lower() == destination.lower():
            flash("Source and destination must be different.", "danger")
            return render_template("offer_ride.html")
        try:
            seats = int(seats_text)
        except ValueError:
            seats = 0
        if not 1 <= seats <= 8:
            flash("Seats must be a number between 1 and 8.", "danger")
            return render_template("offer_ride.html")

        conn = None
        cursor = None
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO rides (user_id, source, destination, seats) VALUES (%s, %s, %s, %s)",
                (session["user_id"], source, destination, seats),
            )
            conn.commit()
            flash("Your ride has been posted.", "success")
            return redirect(url_for("my_rides"))
        except Error as exc:
            if conn:
                conn.rollback()
            app.logger.exception("Offer ride database error: %s", exc)
            flash("Could not post the ride. Please check your database tables.", "danger")
        finally:
            if cursor:
                cursor.close()
            if conn and conn.is_connected():
                conn.close()

    return render_template("offer_ride.html")


@app.route("/rides")
@login_required
def find_rides():
    source = request.args.get("source", "").strip()
    destination = request.args.get("destination", "").strip()
    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        sql = """
            SELECT r.id, r.source, r.destination, r.seats, u.username AS driver
            FROM rides r
            JOIN users u ON u.id = r.user_id
            WHERE r.seats > 0 AND r.user_id <> %s
        """
        params = [session["user_id"]]
        if source:
            sql += " AND r.source LIKE %s"
            params.append("%" + source + "%")
        if destination:
            sql += " AND r.destination LIKE %s"
            params.append("%" + destination + "%")
        sql += " ORDER BY r.id DESC"
        cursor.execute(sql, tuple(params))
        rides = cursor.fetchall()
        return render_template("find_rides.html", rides=rides, source=source, destination=destination)
    except Error as exc:
        app.logger.exception("Find rides database error: %s", exc)
        flash("Could not load rides.", "danger")
        return render_template("find_rides.html", rides=[], source=source, destination=destination)
    finally:
        if cursor:
            cursor.close()
        if conn and conn.is_connected():
            conn.close()


@app.route("/rides/<int:ride_id>/book", methods=["POST"])
@login_required
def book_ride(ride_id):
    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        conn.start_transaction()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT id, user_id, seats FROM rides WHERE id = %s FOR UPDATE", (ride_id,))
        ride = cursor.fetchone()
        if not ride:
            conn.rollback()
            flash("Ride not found.", "danger")
        elif ride["user_id"] == session["user_id"]:
            conn.rollback()
            flash("You cannot book your own ride.", "warning")
        elif ride["seats"] <= 0:
            conn.rollback()
            flash("This ride is full.", "warning")
        else:
            cursor.execute(
                "SELECT id FROM bookings WHERE ride_id = %s AND passenger_id = %s",
                (ride_id, session["user_id"]),
            )
            if cursor.fetchone():
                conn.rollback()
                flash("You have already booked this ride.", "warning")
            else:
                cursor.execute(
                    "INSERT INTO bookings (ride_id, passenger_id, status) VALUES (%s, %s, 'Booked')",
                    (ride_id, session["user_id"]),
                )
                cursor.execute("UPDATE rides SET seats = seats - 1 WHERE id = %s", (ride_id,))
                conn.commit()
                flash("Ride booked successfully.", "success")
    except Error as exc:
        if conn:
            conn.rollback()
        app.logger.exception("Book ride database error: %s", exc)
        flash("Could not book the ride. Please try again.", "danger")
    finally:
        if cursor:
            cursor.close()
        if conn and conn.is_connected():
            conn.close()
    return redirect(url_for("find_rides"))


@app.route("/my-rides")
@login_required
def my_rides():
    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute(
            "SELECT id, source, destination, seats FROM rides WHERE user_id = %s ORDER BY id DESC",
            (session["user_id"],),
        )
        rides = cursor.fetchall()
        return render_template("my_rides.html", rides=rides)
    except Error as exc:
        app.logger.exception("My rides database error: %s", exc)
        flash("Could not load your rides.", "danger")
        return render_template("my_rides.html", rides=[])
    finally:
        if cursor:
            cursor.close()
        if conn and conn.is_connected():
            conn.close()


@app.route("/rides/<int:ride_id>/delete", methods=["POST"])
@login_required
def delete_ride(ride_id):
    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            "DELETE FROM rides WHERE id = %s AND user_id = %s",
            (ride_id, session["user_id"]),
        )
        conn.commit()
        if cursor.rowcount:
            flash("Ride deleted.", "success")
        else:
            flash("Ride not found or you do not own it.", "warning")
    except Error as exc:
        if conn:
            conn.rollback()
        app.logger.exception("Delete ride database error: %s", exc)
        flash("Could not delete the ride. It may have existing bookings.", "danger")
    finally:
        if cursor:
            cursor.close()
        if conn and conn.is_connected():
            conn.close()
    return redirect(url_for("my_rides"))


@app.route("/my-bookings")
@login_required
def my_bookings():
    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute(
            """
            SELECT b.id AS booking_id, b.status, b.booked_at,
                   r.id AS ride_id, r.source, r.destination, u.username AS driver
            FROM bookings b
            JOIN rides r ON r.id = b.ride_id
            JOIN users u ON u.id = r.user_id
            WHERE b.passenger_id = %s
            ORDER BY b.id DESC
            """,
            (session["user_id"],),
        )
        bookings = cursor.fetchall()
        return render_template("my_bookings.html", bookings=bookings)
    except Error as exc:
        app.logger.exception("My bookings database error: %s", exc)
        flash("Could not load your bookings.", "danger")
        return render_template("my_bookings.html", bookings=[])
    finally:
        if cursor:
            cursor.close()
        if conn and conn.is_connected():
            conn.close()


if __name__ == "__main__":
    app.run(debug=True)
