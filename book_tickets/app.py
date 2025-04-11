from sqlite3 import Cursor
from flask import Flask, render_template, request, redirect, url_for, session, flash
from flask_mysqldb import MySQL
import MySQLdb.cursors
import os
import datetime
from dotenv import load_dotenv
import mysql.connector
from datetime import timedelta
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()

load_dotenv()

app = Flask(__name__, static_url_path='/static', static_folder='static')
app.secret_key = "charanteja"

# MySQL Configuration
app.config['MYSQL_HOST'] = os.getenv('MYSQL_HOST', 'localhost')
app.config['MYSQL_USER'] = os.getenv('MYSQL_USER', 'root')
app.config['MYSQL_PASSWORD'] = os.getenv('MYSQL_PASSWORD', 'cherry@16')
app.config['MYSQL_DB'] = os.getenv('MYSQL_DB', 'movie_booking')

mysql = MySQL(app)

app.permanent_session_lifetime = timedelta(minutes=30)

@app.before_request
def make_session_permanent():
    session.permanent = True

@app.route('/')
def landing_page():
    return render_template('landing.html')

@app.route('/about')
def about():
    return render_template('about.html')

@app.route('/contact')
def contact():
    return render_template('contact.html')

@app.route('/index')
def index():
    cursor = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
    cursor.execute("SELECT * FROM movies WHERE is_upcoming = FALSE")
    movies = cursor.fetchall()
    cursor.close()
    return render_template('index.html', movies=movies)

@app.route('/search', methods=['GET'])
def search_movie():
    query = request.args.get('q', '').strip().lower()

    if not query:
        return redirect(url_for('index'))
    cursor = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
    cursor.execute("SELECT id FROM movies WHERE LOWER(name) LIKE %s", (f"%{query}%",))
    movie = cursor.fetchone()

    if movie:
        return redirect(url_for('book', movie_id=movie['id']))
    else:
        return redirect(url_for('index'))

@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        username = request.form['username']
        email = request.form['email']
        password = request.form['password']
        cursor = mysql.connection.cursor()
        cursor.execute('INSERT INTO users (username, email, password) VALUES (%s, %s, %s)', (username, email, password))
        mysql.connection.commit()
        cursor.close()
        flash('Signup successful! Please log in.', 'success')
        return redirect(url_for('login'))
    return render_template('signup.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']
        cursor = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
        cursor.execute('SELECT * FROM users WHERE email = %s AND password = %s', (email, password))
        account = cursor.fetchone()
        cursor.close()
        if account:
            session['loggedin'] = True
            session['user_id'] = account['id']
            session['email'] = account['email']
            session['username'] = account['username']  # 🔥 Add this line!
            return redirect(url_for('index'))
        flash('Invalid email or password', 'danger')
    return render_template('login.html')


@app.route('/dashboard')
def dashboard():
    if 'loggedin' not in session:
        return redirect(url_for('login'))

    user_id = session['user_id']
    cursor = mysql.connection.cursor(MySQLdb.cursors.DictCursor)

    cursor.execute('SELECT username, email FROM users WHERE id = %s', [user_id])
    user = cursor.fetchone()

    cursor.execute('''
        SELECT movies.id AS movie_id, movies.name AS movie_name, bookings.tickets, bookings.booking_date 
        FROM bookings 
        JOIN movies ON bookings.movie_id = movies.id
        WHERE bookings.user_id = %s ORDER BY bookings.booking_date DESC
    ''', [user_id])
    past_bookings = cursor.fetchall()

    cursor.execute('''
        SELECT genre FROM movies 
        JOIN bookings ON movies.id = bookings.movie_id 
        WHERE bookings.user_id = %s 
        GROUP BY genre ORDER BY COUNT(*) DESC LIMIT 1
    ''', [user_id])
    most_booked_genre = cursor.fetchone()

    recommended_movies = []
    if most_booked_genre:
        cursor.execute('''
            SELECT id, name, genre, duration, image_url FROM movies 
            WHERE genre = %s LIMIT 5
        ''', [most_booked_genre['genre']])
        recommended_movies = cursor.fetchall()

    cursor.execute('SELECT id, name, genre, duration, image_url FROM movies WHERE release_date > NOW() LIMIT 5')
    upcoming_movies = cursor.fetchall()
    cursor.close()

    return render_template('dashboard.html', user=user, past_bookings=past_bookings,
                           recommended_movies=recommended_movies, upcoming_movies=upcoming_movies)

@app.route('/account')
def account():
    print("Session contents:", session)  # 👈 Add this for debugging

    if 'username' not in session:
        return redirect(url_for('login'))

    username = session['username']

    cursor = mysql.connection.cursor()
    cursor.execute("SELECT bank_name, account_user, card_number, balance FROM bank_accounts WHERE account_user = %s", (session['username'],))
    row = cursor.fetchone()
    cursor.close()

    if not row:
        account = None
    else:
        account = {
            'bank_name': row[0],
            'account_user': row[1],
            'card_number': row[2],
            'balance': row[3]
        }

    return render_template('account.html', account=account, username=username)


@app.route('/book/<int:movie_id>', methods=['GET', 'POST'])
def book(movie_id):
    session['movie_id'] = movie_id 
    if 'loggedin' not in session:
        return redirect(url_for('login'))

    cursor = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
    cursor.execute('SELECT * FROM movies WHERE id = %s', (movie_id,))
    movie = cursor.fetchone()

    cursor.execute('SELECT * FROM seats WHERE movie_id = %s', (movie_id,))
    seats = cursor.fetchall()
    cursor.close()

    if not movie:
        flash('Movie not found!', 'danger')
        return redirect(url_for('index'))

    if request.method == 'POST':
        selected_seats = request.form.getlist('selected_seats')
        print("🟢 Selected seats from form:", selected_seats)

        tickets = len(selected_seats)
        if tickets == 0:
            flash("No seats selected! Please select at least one seat.", "warning")
            return redirect(url_for('book', movie_id=movie_id))

        cursor = mysql.connection.cursor()
        try:
            # Check for already booked seats
            placeholders = ','.join(['%s'] * len(selected_seats))
            seat_check_query = f'''
                SELECT seat_number FROM seats
                WHERE movie_id = %s AND seat_number IN ({placeholders}) AND is_booked = 1
            '''
            cursor.execute(seat_check_query, (movie_id, *selected_seats))
            already_booked = cursor.fetchall()

            if already_booked:
                booked_list = ', '.join(seat['seat_number'] for seat in already_booked)
                flash(f"The following seats are already booked: {booked_list}", "danger")
                cursor.close()
                return redirect(url_for('book', movie_id=movie_id))

            # Create booking entry
            total_price = movie['price'] * tickets
            print("✅ Inserting booking for user:", session['user_id'], "Total price:", total_price)
            cursor.execute(
                'INSERT INTO bookings (user_id, movie_id, tickets, total_price, booking_date) VALUES (%s, %s, %s, %s, NOW())',
                (session['user_id'], movie_id, tickets, total_price)
            )
            booking_id = cursor.lastrowid
            print("✅ Booking ID:", booking_id)

            # Update seats
            for seat_number in selected_seats:
                print("📌 Booking seat:", seat_number)
                cursor.execute(
                    'UPDATE seats SET is_booked = TRUE, booking_id = %s  WHERE movie_id = %s AND seat_number = %s',
                    (booking_id, movie_id, seat_number)
                )

            mysql.connection.commit()

            # Store booking info in session
            session['current_booking_id'] = booking_id
            session['selected_seats'] = selected_seats
            session['total_price'] = total_price
            session['movie_id'] = movie_id


            #flash('Booking successful! Proceed to payment.', 'success')
            return redirect(url_for('payment'))

        except Exception as e:
            mysql.connection.rollback()
            print("🔴 Booking Error:", str(e))
            flash('An error occurred during booking.', 'danger')

        finally:
            cursor.close()

    return render_template('booking.html', movie=movie, seats=seats)


@app.route('/payment', methods=['GET', 'POST'])
def payment():
    if 'loggedin' not in session or 'current_booking_id' not in session:
        flash("Please login and make a booking first.", "warning")
        return redirect(url_for('login'))

    user_id = session['user_id']
    booking_id = session['current_booking_id']
    movie_id = session.get('movie_id')
    selected_seats = session.get('selected_seats', [])
    total_price = session.get('total_price')

    cursor = mysql.connection.cursor(MySQLdb.cursors.DictCursor)

    if request.method == 'POST':
        bank_name = request.form.get('bank_name')
        card_number = request.form.get('card_number')
        cvv = request.form.get('cvv')
        expiry = request.form.get('expiry')
        print("Bank details entered:", bank_name, card_number, cvv, expiry)

        if not all([bank_name, card_number, cvv, expiry, total_price]):
            flash("Please fill in all bank details.", "danger")
            return redirect(url_for('payment'))

        try:
            total_price = float(total_price)
        except ValueError:
            flash("Invalid amount.", "danger")
            return redirect(url_for('payment'))

        cursor.execute('''
        SELECT * FROM bank_accounts
        WHERE account_user = %s AND bank_name = %s AND card_number = %s AND cvv = %s AND expiry = %s
        ''', (session['username'], bank_name, card_number, cvv, expiry))

        bank = cursor.fetchone()
        print("Bank verification result:", bank)

        if not bank:
            flash("Invalid or unauthorized bank details.", "danger")
            return redirect(url_for('payment'))

        if bank['balance'] < total_price:
            flash("Insufficient balance. Payment failed.", "danger")
            return redirect(url_for('payment'))

        try:
            new_balance = float(bank['balance']) - total_price
            cursor.execute('UPDATE bank_accounts SET balance = %s WHERE id = %s', (new_balance, bank['id']))

            cursor.execute('''
                INSERT INTO payments (booking_id, user_id, bank_name, card_number, cvv, expiry, amount, payment_time, status)
                VALUES (%s, %s, %s, %s, %s, %s, %s, NOW(), %s)
            ''', (booking_id, user_id, bank_name, card_number, cvv, expiry, total_price, 'Success'))

            cursor.execute('''
                UPDATE bookings SET booking_date = NOW(), total_price = %s WHERE id = %s
            ''', (total_price, booking_id))

            for seat in selected_seats:
                cursor.execute('''
                UPDATE seats SET is_booked = 1, booking_id = %s
                WHERE seat_number = %s AND movie_id = %s
                ''', (booking_id, seat, movie_id))


            mysql.connection.commit()
            cursor.close()

            # ✅ DO NOT REMOVE current_booking_id yet
            session['payment_done'] = True
            return redirect(url_for('confirmation'))

        except Exception as e:
            mysql.connection.rollback()
            cursor.close()
            print("Payment Error:", e)
            flash("An error occurred while processing your payment. Please try again.", "danger")
            return redirect(url_for('payment'))

    cursor.execute('''
        SELECT b.*, m.name AS movie_name, m.image_url AS movie_image 
        FROM bookings b 
        JOIN movies m ON b.movie_id = m.id 
        WHERE b.id = %s AND b.user_id = %s
    ''', (booking_id, user_id))
    booking = cursor.fetchone()

    cursor.execute('SELECT * FROM bank_accounts WHERE account_user = %s', (user_id,))
    bank_account = cursor.fetchone()
    cursor.close()

    if not booking:
        flash("No valid booking found.", "danger")
        return redirect(url_for('index'))

    return render_template('payment.html', booking=booking, bank=bank_account)


@app.route('/confirmation')
def confirmation():
    if 'loggedin' not in session:
        flash("Please login to continue.", "warning")
        return redirect(url_for('login'))

    if not session.get('payment_done'):
        flash("Please complete payment to access confirmation.", "warning")
        return redirect(url_for('dashboard'))
    
    booking_id = session.get('current_booking_id')
    if not booking_id:
        flash("Booking session expired. Please check your dashboard.", "warning")
        return redirect(url_for('dashboard'))

    cursor = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
    cursor.execute('''
        SELECT b.*, m.name AS movie_name, m.image_url AS movie_image
        FROM bookings b
        JOIN movies m ON b.movie_id = m.id
        WHERE b.id = %s AND b.user_id = %s
    ''', (booking_id, session['user_id']))
    booking_details = cursor.fetchone()

    if booking_details and booking_details['booking_date']:
        booking_details['booking_date'] = booking_details['booking_date'].strftime('%d %b %Y, %I:%M %p')

    selected_seats = session.get('selected_seats', [])
    booking_details['selected_seats'] = ', '.join(selected_seats)

    cursor.close()

    # ✅ Clear session keys now
    session.pop('current_booking_id', None)
    session.pop('payment_done', None)
    session.pop('selected_seats', None)
    session.pop('total_price', None)

    return render_template('confirmation.html', booking=booking_details)


@app.route('/logout')
def logout():
    session.clear()
    flash("You have been logged out.", "info")
    return redirect(url_for('landing_page'))

if __name__ == '__main__':
    app.run(debug=True)
