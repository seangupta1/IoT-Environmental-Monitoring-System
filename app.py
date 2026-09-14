import os
import time
import json
import requests
from datetime import datetime, timedelta, timezone
from flask import Flask, request, render_template, redirect, url_for, session
from flask_bcrypt import Bcrypt
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from dotenv import load_dotenv
from models import ReadingBase
from pydantic import ValidationError

from db import db
from schemas.user import User
from schemas.reading import Reading
from crud import reading, user
from utils import decrypt_data, get_current_utc_time

# load environment variables from the .env file
load_dotenv()

app = Flask(__name__)

# Prevent page caching
app.config['SEND_FILE_MAX_AGE_DEFAULT'] = 0

# encrypt the session cookie with secret key
app.secret_key = os.getenv("FLASK_SECRET_KEY")

# Tell SQLAlchemy where to build the physical SQLite file
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///server.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# connect Flask to the database through SQLAlchemy
db.init_app(app)

# Initialize the security tools
bcrypt = Bcrypt(app)  # encrypts passwords and checks them during login
login_manager = LoginManager(app)  # tracks who is logged in.
login_manager.login_view = 'login'


#  active app context to interact with the database
with app.app_context():
    # Looks at schemas. If server.db doesn't have those tables, builds them
    db.create_all()
    
    new_admin = user.create(username="admin", password="admin", role="Admin", bcrypt=bcrypt)
    if new_admin:
        print("--- Admin Account Created: Use 'admin' and 'admin' ---")
        
    new_test_user = user.create(username="testuser", password="password123", role="User", bcrypt=bcrypt)    
    if new_test_user:
        print("--- User Account Created: Use 'testuser' and 'password123' ---")

# dictionary linking User IDs to the exact time they last clicked a button.
user_activity = {}

# Prevent page caching so user cant return to protected area after logging out
@app.after_request
def add_security_headers(response):
    """Add headers to prevent page caching."""
    response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '0'
    return response

# Runs before any webpage for a user is loaded
# if the user is logged in, update their last active time in user_activity dict
@app.before_request
def track_user_activity():
    if current_user.is_authenticated:
        user_activity[current_user.id] = get_current_utc_time()


# finds user in the database by unique ID and load info into 'current_user'
@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))


@app.route('/login', methods=['GET', 'POST'])
def login():
    # POST means the user clicked the "Submit" button on the form
    if request.method == 'POST':
        # Grab the text they typed into the username and password boxes
        username = request.form.get('username')
        password = request.form.get('password')

        logging_in_user = user.read(username=username, password=password, bcrypt=bcrypt)

        if logging_in_user:
            login_user(logging_in_user)
            session["role"] = logging_in_user.role
            return redirect(url_for('index'))
        else:
            print("Invalid login attempt")

    # Failed login or GET means user just navigated to /login
    return render_template('login.html')


@app.route('/logout')
def logout():
    logout_user()
    session.clear()
    print("User logged out successfully.")
    return redirect(url_for('login'))  # return back to the login screen.


# dashboard page. This is the main page users see when they log in.
@app.route('/dashboard')
@login_required
def index():
    # Fetch the data but don't unpack
    latest_data = reading.read_latest()

    if latest_data is None:
        timestamp = datetime.now(timezone.utc)
        temperature, humidity = "N/A", "N/A"
    else:
        timestamp, temperature, humidity = latest_data

    # get last 200 readings for the charts.
    readings = reading.read_all(num_samples=200)
    readings.reverse()

    # JavaScript's Chart.js needs data separated into specific lists
    labels = [r.timestamp.isoformat() for r in readings]
    temperatures = [r.temperature for r in readings]
    humidities = [r.humidity for r in readings]

    # check if user is searching for something specific.
    # If so, grab the search rules from the browser session.
    threshold_temperature = session.get('threshold_temperature')
    direction = session.get('direction')
    start_datetime_str = session.get('start_datetime')
    end_datetime_str = session.get('end_datetime')

    search_results = None

    # search crud/reading.py with those rules
    if threshold_temperature or start_datetime_str or end_datetime_str:
        #  HTML forms use local time, but database is in UTC. shift the time +5 hours to match
        start_date = datetime.fromisoformat(start_datetime_str) + timedelta(hours=5) if start_datetime_str else None
        end_date = datetime.fromisoformat(end_datetime_str) + timedelta(hours=5) if end_datetime_str else None

        search_results = reading.read_search(
            threshold_temperature=threshold_temperature,
            direction=direction,
            start_date=start_date,
            end_date=end_date
        )

        if search_results is None:
            search_results = []

    # Build dhashboard.html by injecting all this data into the template.
    return render_template(
        "dashboard.html",
        user=current_user,
        user_role=session["role"],
        current_timestamp=timestamp,
        current_temperature=temperature,
        current_humidity=humidity,
        labels=json.dumps(labels),
        temperatures=json.dumps(temperatures),
        humidities=json.dumps(humidities),
        search_results=search_results
    )


# info dashboard page.
@app.route('/info')
@login_required
def info_dashboard():
    start_time = time.perf_counter()
    total_records = Reading.query.count()
    # how long to count all records in the database
    query_efficiency = (time.perf_counter() - start_time) * 1000

    # determine active users: Count how many users clicked a link in last 5 min
    cutoff_time = get_current_utc_time() - timedelta(minutes=5)
    active_count = sum(1 for last_seen in user_activity.values() if last_seen > cutoff_time)

    # Calculate Database Throughput: Count exactly how many records the ESP32 uploaded in the last 60 seconds.
    one_minute_ago = get_current_utc_time() - timedelta(minutes=1)
    recent_count = Reading.query.filter(Reading.timestamp >= one_minute_ago).count()
    throughput = f"{recent_count} records/min"

    # for encryption visual
    latest = Reading.query.order_by(Reading.id.desc()).first() 
    sample_payload = {
        "temp": latest.temperature if latest else "N/A",
        "hum": latest.humidity if latest else "N/A",
        "encrypted_blob": "AES_ENCRYPTED_DATA_DETECTED" if latest else "WAITING..."
    }

    # Inject all this diagnostic data into the info.html template.
    return render_template(
        "info.html",
        user=current_user,
        active_sessions=active_count,
        total_records=total_records,
        query_efficiency=f"{query_efficiency:.2f}ms",
        throughput=throughput,
        latest_data=sample_payload,
        user_count=User.query.count(),
        all_users=User.query.all() # Hands a list of every user to the HTML
    )


@app.route('/submit-temperature-search', methods=['POST'])
def temperature_search():
    # Grabs the data from the Search Form on the dashboard
    threshold = request.form.get('threshold_temperature')
    direction = request.form.get('direction')
    start = request.form.get('start_time')
    end = request.form.get('end_time')

    # Saves those rules into the browser's 'session' memory so they don't disappear when the page reloads
    session["threshold_temperature"] = threshold
    session["direction"] = direction
    session["start_datetime"] = start
    session["end_datetime"] = end

    # Refresh the page by sending the user back to the index function
    return redirect(url_for("index"))


@app.route('/clear-temperature-search', methods=['POST'])
def clear_search():
    # Deletes the search rules from the browser's session memory, resetting the filters
    session.pop("threshold_temperature", None)
    session.pop("direction", None)
    session.pop("start_datetime", None)
    session.pop("end_datetime", None)
    return redirect(url_for("index"))


user_activity = {}
total_records_cache = None


# waits for the ESP32 hardware to send a JSON payload.
@app.route('/post-data', methods=['POST'])
def receive_data():
    global total_records_cache
    payload = request.get_json()

    try:
        # Hand the payload to Pydantic (ReadingBase) for cleaning and validation
        clean_data = ReadingBase(**payload)

        reading.create(temperature=clean_data.temperature, humidity=clean_data.humidity)

        if total_records_cache is not None:
            total_records_cache += 1

        # Reply to the ESP32 to let it know the data was received and saved
        return {"status": "success"}, 200
    except ValidationError as e:
        return {"error": "Invalid data format", "details": e.errors()}, 400
    except Exception as e:
        return {"error": str(e)}, 500


# called by JavaScript on the dashboard every 30 seconds to get the newest reading without refreshing the page.
@app.route('/api/latest-readings')
def latest_readings():
    # updates the "Current Readings" box on the dashboard
    latest = Reading.query.order_by(Reading.timestamp.desc()).first()
    if latest:
        return {
            "temperature": latest.temperature,
            "humidity": latest.humidity,
            "timestamp": latest.timestamp.isoformat()
        }
    return {"temperature": "N/A", "humidity": "N/A", "timestamp": None}, 200


# called by JavaScript on the dashboard every 30 seconds to get the newest reading without refreshing the page.
@app.route('/api/system-status')
@login_required
def system_status():
    global total_records_cache

    start_time = time.perf_counter()
    # updates the 'System Diagnostics' boxes on the Info page.
    latest = Reading.query.order_by(Reading.timestamp.desc()).first()

    # use raw SQL here to pull the physical encrypted string out of the database without python auto-decrypting it first.
    raw_row = db.session.execute(db.text("SELECT temperature, humidity FROM readings ORDER BY id DESC LIMIT 1")).fetchone()

    if total_records_cache is None:
        total_records_cache = Reading.query.count()

    efficiency_ms = (time.perf_counter() - start_time) * 1000

    if not latest or not raw_row:
        return {
            "temp": "N/A", "hum": "N/A",
            "raw_t": "N/A", "raw_h": "N/A",
            "count": total_records_cache,
            "efficiency": f"{efficiency_ms:.2f}ms",  # Add to JSON
            "status": "WAITING FOR DATA...",
            "timestamp": None
        }, 200

    now = get_current_utc_time()
    last_time = latest.timestamp

    # SQLite drops timezone info, making it "naive". We force it back to UTC "aware" here.
    if last_time.tzinfo is None:
        last_time = last_time.replace(tzinfo=timezone.utc)

    time_since_last = now - last_time

    # If the reading is older than 30 seconds, consider the stream dead
    if time_since_last.total_seconds() > 30:
        return {
            "temp": "--",
            "hum": "--",
            "raw_t": "--",
            "raw_h": "--",
            "count": total_records_cache,
            "efficiency": f"{efficiency_ms:.2f}ms",
            "status": "CONNECTION LOST / WAITING...",
            # Keep sending the timestamp so the UI shows exactly when it died
            "timestamp": latest.timestamp.isoformat() + "Z" if latest.timestamp else None
        }, 200

    is_encrypted = str(raw_row[0]) != str(latest.temperature)
    current_status = "AES ENCRYPTED PAYLOAD DETECTED" if is_encrypted else "PLAINTEXT DATA DETECTED"

    return {
        "temp": latest.temperature,
        "hum": latest.humidity,
        "raw_t": raw_row[0],
        "raw_h": raw_row[1],
        "count": total_records_cache,
        "efficiency": f"{efficiency_ms:.2f}ms", # Add to JSON
        "status": current_status,
        "timestamp": latest.timestamp.isoformat() + "Z"
    }, 200


# A memory dictionary. Save weather result here with timestamp. If same city
# requested again within 10 minutes, serve saved copy instead of hitting API again.
weather_cache = {}
CACHE_TIMEOUT = 600  # 10 minutes (in seconds)


@app.route('/api/weather')
def get_weather():
    # default to Kansas City if no city provided
    city = request.args.get('city', 'Kansas City')  
    current_time = time.time()

    # Check if we have asked the API about this city recently.
    if city in weather_cache:
        cached_data = weather_cache[city]
        # If the saved copy is less than 10 minutes old, serve that copy
        if current_time - cached_data['timestamp'] < CACHE_TIMEOUT:
            return cached_data['data']

    # If no saved copy, get the secret API key from .env file
    api_key = os.getenv("WEATHER_API_KEY")
    if not api_key:
        return {"error": "API key missing. Check .env file."}, 500

    # Build URL and send GET request out to internet using 'requests' library.
    url = f"http://api.weatherapi.com/v1/current.json?key={api_key}&q={city}"
    try:
        response = requests.get(url)
        data = response.json()

        # If the weather API responded with a success, save a copy in our cache for the next 10 minutes.
        if "error" not in data:
            weather_cache[city] = {
                'data': data,
                'timestamp': current_time
            }
        return data
    except Exception as e:
        return {"error": str(e)}, 500
    
@app.route('/register')
def register_page():
    return render_template("register.html")

@app.route('/register_account', methods=['POST'])
def register_account():
    # Grab the text they typed into the username and password boxes
    username = request.form.get('username')
    password = request.form.get('password')

    if not user.create(username=username, password=password, role="User", bcrypt=bcrypt):
        print("Attempt to create account with username failed.")
        return redirect(url_for('register_page'))

    return redirect(url_for('login'))

@app.route('/')
def home():
    # This automatically sends the user to the login page if they just type the IP address
    return redirect(url_for('login'))

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=8888)
