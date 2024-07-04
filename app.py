import os
import io
import nltk
import speech_recognition as sr
from nltk.sentiment import SentimentIntensityAnalyzer
from flask import Flask, render_template, request, session, redirect, jsonify
import mysql.connector
import matplotlib
matplotlib.use('Agg')  # Use Agg backend for non-interactive mode
import matplotlib.pyplot as plt
import base64
import json
from nltk.sentiment.vader import SentimentIntensityAnalyzer
import random

app = Flask(__name__)
app.secret_key = os.urandom(24)

# Connect to the database
mydb = mysql.connector.connect(
    host="localhost",
    user="root",
    password="Mahesh@123",
    database="saoivc"
)
mycursor = mydb.cursor()

# Initialize NLTK and SentimentIntensityAnalyzer
sia = SentimentIntensityAnalyzer()
nltk.download('vader_lexicon')

# Initialize the recognizer
r = sr.Recognizer()

@app.route('/chart')
def chart():
    plot_url = generate_chart()
    if plot_url is None:
        return render_template('chart.html', plot_url=None, message="No sentiment data available.")
    return render_template('chart.html', plot_url=plot_url, message=None)

# Define route for the landing page and user login
@app.route('/', methods=['GET', 'POST'])
def index():
    if 'user' in session:
        # Check if the user is an admin
        if session.get('user_type') == 'admin':
            return redirect('/dashboard')
        else:
            return render_template('index.html', name=session.get('user'))  # Redirect to index page
    else:
        if request.method == 'POST':
            if request.form['action'] == 'signup':
                return redirect('/signup')
            elif request.form['action'] == 'login':
                return redirect('/login')
        return render_template('landing.html')

# Define route for signup page
@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        user_type = request.form.get('user_type')

        if not username or not password or not user_type:
            return render_template('signup.html', message="Please provide all the required information")

        # Check if user already exists
        mycursor.execute("SELECT * FROM customer WHERE username = %s", (username,))
        existing_user = mycursor.fetchone()

        if existing_user:
            return render_template('signup.html', message="User already exists")

        # Insert new user into the database
        query = "INSERT INTO customer (username, password, user_type) VALUES (%s, %s, %s)"
        values = (username, password, user_type)
        mycursor.execute(query, values)
        mydb.commit()  # Commit changes to the database

        # Redirect to login page after successful signup
        return redirect('/login')
    
    return render_template('signup.html')

# Function to authenticate user
def authenticate_user(username, password):
    mycursor.execute("SELECT * FROM customer WHERE username = %s AND password = %s", (username, password))
    user = mycursor.fetchone()
    return user

# Inside the login route
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        if not username or not password:
            return render_template('login.html', message="Please provide both username and password")
        
        user = authenticate_user(username, password)
        if user:
            session['user_id'] = user[0]  # Assuming user ID is the first column in the users table
            session['user'] = username
            
            # Check user type and redirect accordingly
            if user[3] == 'admin':
                session['user_type'] = 'admin'  # Add user type to the session
                return redirect('/dashboard')
            else:
                session['user_type'] = 'customer'  # Add user type to the session
                return redirect('/details')
        else:
            return render_template('login.html', message="Invalid username or password")
    
    return render_template('login.html')

# Route for the user details page
@app.route('/details')
def user_details():
    if 'user' in session:
        user_type = session.get('user_type')
        if user_type == 'admin':
            return redirect('/dashboard')
        else:
            name = session.get('user')
            return render_template('index.html', name=name)  # Pass name to the template
    else:
        return redirect('/login')
    
# Route for submitting user details (if needed)
@app.route('/submit_details', methods=['POST'])
def submit_details():
    if request.method == 'POST':
        # Extract form data
        name = request.form.get('name')
        contact_number = request.form.get('contact_number')
        email = request.form.get('email')
        age = request.form.get('age')
        gender = request.form.get('gender')
        company = request.form.get('company')
        product = request.form.get('product')
        
        # Get customer ID from session
        customer_id = session.get('user_id')

        if not customer_id:
            return jsonify({"success": False, "error_message": "User ID not found in session"})

        sql = "INSERT INTO user_details (name, contact_number, email, age, gender, company, product, customer_id) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)"
        values = (name, contact_number, email, age, gender, company, product, customer_id)

        try:
            mycursor.execute(sql, values)
            mydb.commit()
            # Redirect to the sentiment_analysis route
            return jsonify({"success": True, "redirect_url": "/sentiment_analysis"})
        except Exception as e:
            print("Error:", e)
            return jsonify({"success": False, "error_message": "Failed to store user details"})
    else:
        return "Method Not Allowed", 405


# Function to record audio and convert to text
def record_text():
    try:
        with sr.Microphone() as source:
            print("Recording...")
            r.adjust_for_ambient_noise(source, duration=0.5)  # Adjust the duration to better detect pauses
            audio = r.listen(source)
            print("Recording finished.")
        text = r.recognize_google(audio)
        return text
    except sr.RequestError as e:
        print("Could not request results from Google Speech Recognition service; {0}".format(e))
        return None
    except sr.UnknownValueError:
        print("Google Speech Recognition could not understand audio")
        return None
    
@app.route('/sentiment_analysis', methods=['GET', 'POST'])
def sentiment_analysis():
    # Check if the user is logged in
    if 'user' not in session:
        return redirect('/login')
    
    sentiment = None  # Initialize sentiment variable
    transcribed_text = None
    plot_url = None

    if request.method == 'POST':
        # Check if an audio file was submitted
        if 'audio' not in request.files:
            return jsonify({'error': 'No audio file provided'})

        audio_option = request.form.get('audio-option')

        # If the audio option is "Live"
        if audio_option == 'live':
            # Call record_text function to get transcribed text from live audio
            audio_text = record_text()

            if audio_text:
                transcribed_text = audio_text

                # Analyze sentiment
                sentiment_scores = analyze_sentiment(transcribed_text)

                if sentiment_scores:
                    compound_score = sentiment_scores['compound']
                    if compound_score >= 0.05:
                        sentiment = 'positive'
                    elif compound_score <= -0.05:
                        sentiment = 'negative'
                    else:
                        sentiment = 'neutral'

                    # Get username from session
                    username = session.get('user')

                    # Lookup customer ID using username
                    mycursor.execute("SELECT customer_id FROM customer WHERE username = %s", (username,))
                    result = mycursor.fetchone()

                    if result:
                        customer_id = result[0]  # Extract customer ID from the result

                        # Get user_id from session
                        user_id = session.get('user_id')

                    # Store analysis result in the database
                    store_analysis_result(transcribed_text, sentiment, compound_score, customer_id, user_id)

        # If the audio option is "Recorded"
        elif audio_option == 'recorded':
            audio_file = request.files['audio']
            if audio_file.filename == '':
                return jsonify({'error': 'No file selected'})
            if audio_file:
                file_extension = os.path.splitext(audio_file.filename)[1]
                if file_extension.lower() != '.wav':
                    return jsonify({'error': 'Invalid file format. Please upload a .wav file.'})

                audio_file_path = 'uploaded_audio.wav'
                audio_file.save(audio_file_path)  # Save the uploaded audio file
                recorded_text = analyze_recorded_audio(audio_file_path)

                if recorded_text:
                    transcribed_text = recorded_text

                    # Analyze sentiment
                    sentiment_scores = analyze_sentiment(transcribed_text)

                    if sentiment_scores:
                        compound_score = sentiment_scores['compound']
                        if compound_score >= 0.05:
                            sentiment = 'positive'
                        elif compound_score <= -0.05:
                            sentiment = 'negative'
                        else:
                            sentiment = 'neutral'

                    # Get username from session
                    username = session.get('user')

                    # Lookup customer ID using username
                    mycursor.execute("SELECT customer_id FROM customer WHERE username = %s", (username,))
                    result = mycursor.fetchone()

                    if result:
                        customer_id = result[0]  # Extract customer ID from the result

                        # Get user_id from session
                        user_id = session.get('user_id')

                        # Store analysis result in the database
                        store_analysis_result(transcribed_text, sentiment, compound_score, customer_id, user_id)

    # Fetch data from the database for pie chart
    mycursor.execute("SELECT sentiment, COUNT(*) FROM Transcriptions GROUP BY sentiment")
    sentiments = mycursor.fetchall()
    labels = [sentiment[0] for sentiment in sentiments]
    counts = [sentiment[1] for sentiment in sentiments]

    # Plotting the pie chart
    if labels and counts:
        fig, ax = plt.subplots()
        ax.pie(counts, labels=labels, autopct='%1.1f%%', startangle=90)
        ax.axis('equal')  # Equal aspect ratio ensures that pie is drawn as a circle.

        # Convert plot to PNG image
        img = io.BytesIO()
        plt.savefig(img, format='png')
        img.seek(0)
        plot_url = base64.b64encode(img.getvalue()).decode()

    return render_template('sentiment_analysis.html', sentiment=sentiment, transcribed_text=transcribed_text, plot_url=plot_url)
    
def analyze_recorded_audio(file_path):
    with sr.AudioFile(file_path) as source:
        audio_text = r.record(source)
        text = r.recognize_google(audio_text)
        return text
    
# Function to convert audio to text and get sentiment score
def analyze_sentiment(text):
    sentiment_scores = sia.polarity_scores(text)
    return sentiment_scores

def store_analysis_result(text, sentiment, compound_score, customer_id, user_id):
    try:
        mycursor = mydb.cursor()

        # Insert the analysis result into Transcriptions table
        sql_transcriptions = "INSERT INTO Transcriptions (transcripted_text, sentiment, compound_score, customer_id, user_id) VALUES (%s, %s, %s, %s, %s)"
        values_transcriptions = (text, sentiment, compound_score, customer_id, user_id)

        print("Executing SQL query:", sql_transcriptions)  # Debugging output
        print("Values to insert:", values_transcriptions)  # Debugging output

        mycursor.execute(sql_transcriptions, values_transcriptions)
        mydb.commit()

        print("Transcriptions table updated successfully.")
    except Exception as e:
        print("Error during database operation:", e)

# Extracted function for getting and plotting sentiment data
def generate_chart():
    mycursor.execute("SELECT sentiment, COUNT(*) FROM Transcriptions GROUP BY sentiment")
    sentiments = mycursor.fetchall()
    labels = [sentiment[0] for sentiment in sentiments]
    counts = [sentiment[1] for sentiment in sentiments]

    # Check if there are sentiments to plot
    if not labels or not counts:
        return None

    fig, ax = plt.subplots()
    ax.pie(counts, labels=labels, autopct='%1.1f%%', startangle=90)
    ax.axis('equal')  # Equal aspect ratio ensures that pie is drawn as a circle.

    img = io.BytesIO()
    plt.savefig(img, format='png', bbox_inches='tight')
    plt.close(fig)  # Close the figure to free memory
    img.seek(0)
    return base64.b64encode(img.getvalue()).decode()

# Define route for displaying the live pie chart
@app.route('/live_chart')
def live_chart():
    plot_url = generate_chart()
    if plot_url is None:
        return render_template('chart.html', plot_url=None, message="No sentiment data available.")
    return render_template('chart.html', plot_url=plot_url, message=None)

# Inside the route for the dashboard page
@app.route('/dashboard')
def dashboard():
    if 'user' not in session:
        return redirect('/login')

    # Check if the user is an admin
    if session.get('user') and session.get('user_type') == 'admin':
        try:
            # Query to fetch gender distribution data from user_details table
            mycursor.execute("SELECT gender, COUNT(*) FROM user_details GROUP BY gender")
            gender_result = mycursor.fetchall()

            # Extracting data for gender distribution pie chart
            gender_labels = [gender[0] for gender in gender_result]
            gender_counts = [gender[1] for gender in gender_result]

            # Plotting gender distribution pie chart
            plt.figure(figsize=(6, 6))
            plt.pie(gender_counts, labels=gender_labels, autopct='%1.1f%%', startangle=140)
            plt.axis('equal')
            plt.title('Gender Distribution')
            plt.tight_layout()

            # Save gender distribution pie chart to a bytes object
            gender_img = io.BytesIO()
            plt.savefig(gender_img, format='png')
            gender_img.seek(0)
            gender_plot_url = base64.b64encode(gender_img.getvalue()).decode()

            # Render dashboard with gender distribution pie chart
            return render_template('dashboard.html', gender_plot_url=gender_plot_url)
        except Exception as e:
            print("Error:", e)
            return render_template('dashboard.html', error="Failed to fetch data for dashboard")
    else:
        return redirect('/login')

# Extracted function for getting and plotting gender distribution data
def generate_gender_chart():
    mycursor.execute("SELECT gender, COUNT(*) FROM user_details GROUP BY gender")
    genders = mycursor.fetchall()
    labels = [gender[0] for gender in genders]
    counts = [gender[1] for gender in genders]

    # Check if there are gender data to plot
    if not labels or not counts:
        return None

    fig, ax = plt.subplots()
    ax.pie(counts, labels=labels, autopct='%1.1f%%', startangle=90)
    ax.axis('equal')  # Equal aspect ratio ensures that pie is drawn as a circle.

    img = io.BytesIO()
    plt.savefig(img, format='png', bbox_inches='tight')
    plt.close(fig)  # Close the figure to free memory
    img.seek(0)
    return base64.b64encode(img.getvalue()).decode()

# Define route for displaying the live gender distribution chart
@app.route('/gender_distribution')
def gender_distribution():
    plot_url = generate_gender_chart()
    if plot_url is None:
        return render_template('gender_chart.html', plot_url=None, message="No gender distribution data available.")
    return render_template('gender_chart.html', plot_url=plot_url, message=None)

# Extracted function for getting and plotting age distribution data
def generate_age_chart():
    # Define age categories
    age_categories = ['0-18', '19-35', '36-50', '51+']

    # Initialize counts for each category
    category_counts = [0] * len(age_categories)

    # Fetch age data from the database
    mycursor.execute("SELECT age FROM user_details")
    ages = mycursor.fetchall()

    # Calculate counts for each age category
    for age in ages:
        if age[0] <= 18:
            category_counts[0] += 1
        elif age[0] <= 35:
            category_counts[1] += 1
        elif age[0] <= 50:
            category_counts[2] += 1
        else:
            category_counts[3] += 1

    # Check if there are age data to plot
    if sum(category_counts) == 0:
        return None

    fig, ax = plt.subplots()
    ax.pie(category_counts, labels=age_categories, autopct='%1.1f%%', startangle=90)
    ax.axis('equal')  # Equal aspect ratio ensures that pie is drawn as a circle.

    img = io.BytesIO()
    plt.savefig(img, format='png', bbox_inches='tight')
    plt.close(fig)  # Close the figure to free memory
    img.seek(0)
    return base64.b64encode(img.getvalue()).decode()

# Define route for displaying the live age distribution chart
@app.route('/age_distribution')
def age_distribution():
    plot_url = generate_age_chart()
    if plot_url is None:
        return render_template('age_chart.html', plot_url=None, message="No age distribution data available.")
    return render_template('age_chart.html', plot_url=plot_url, message=None)

# Initialize the Sentiment Intensity Analyzer
sid = SentimentIntensityAnalyzer()

def generate_latest_sentiment_chart():
    # Fetch the latest entry from the Transcriptions table
    mycursor.execute("SELECT transcripted_text FROM Transcriptions ORDER BY trans_id DESC LIMIT 1")
    latest_entry = mycursor.fetchone()

    if latest_entry is None:
        return None

    # Perform sentiment analysis on the latest entry
    sentiment = sid.polarity_scores(latest_entry[0])

    # Calculate percentage for the actual sentiment
    actual_percentage = abs(sentiment['compound']) * 100

    # Calculate remaining percentage
    remaining_percentage = 100 - actual_percentage

    # Initialize percentages
    positive_percentage = 0
    negative_percentage = 0
    neutral_percentage = 0

    # Adjust percentages based on sentiment
    if sentiment['compound'] > 0:
        positive_percentage = actual_percentage
        negative_percentage = remaining_percentage / 3
        neutral_percentage = 2 * (remaining_percentage / 3)
    elif sentiment['compound'] < 0:
        negative_percentage = actual_percentage
        positive_percentage = remaining_percentage / 3
        neutral_percentage = 2 * (remaining_percentage / 3)
    else:
        # For neutral sentiment, distribute remaining percentage as specified
        neutral_percentage = 65
        positive_percentage = 2 * (100 - neutral_percentage) / 3
        negative_percentage = (100 - neutral_percentage) / 3

    # Plot the pie chart
    fig, ax = plt.subplots()
    if sentiment['compound'] > 0:
        ax.pie([positive_percentage, negative_percentage, neutral_percentage], labels=['Positive', 'Negative', 'Neutral'], autopct='%1.1f%%', startangle=90)
    elif sentiment['compound'] < 0:
        ax.pie([negative_percentage, positive_percentage, neutral_percentage], labels=['Negative', 'Positive', 'Neutral'], autopct='%1.1f%%', startangle=90)
    else:
        ax.pie([neutral_percentage, positive_percentage, negative_percentage], labels=['Neutral', 'Positive', 'Negative'], autopct='%1.1f%%', startangle=90)
    ax.axis('equal')  # Equal aspect ratio ensures that pie is drawn as a circle.

    img = io.BytesIO()
    plt.savefig(img, format='png', bbox_inches='tight')
    plt.close(fig)  # Close the figure to free memory
    img.seek(0)
    return base64.b64encode(img.getvalue()).decode()

# Define route for displaying the live sentiment analysis chart for the latest entry
@app.route('/latest_sentiment_chart')
def latest_sentiment_chart():
    plot_url = generate_latest_sentiment_chart()
    if plot_url is None:
        return render_template('recent.html', plot_url=None, message="No data available.")
    return render_template('recent.html', plot_url=plot_url, message=None)

# Extracted function for getting and plotting company distribution data
def generate_company_chart():
    # Fetch company distribution data from the database
    mycursor.execute("SELECT company, COUNT(*) FROM user_details GROUP BY company")
    company_data = mycursor.fetchall()

    # Check if there is company data to plot
    if not company_data:
        return None

    companies = [company[0] for company in company_data]
    counts = [company[1] for company in company_data]

    # Plotting the company distribution pie chart
    fig, ax = plt.subplots()
    ax.pie(counts, labels=companies, autopct='%1.1f%%', startangle=90)
    ax.axis('equal')  # Equal aspect ratio ensures that pie is drawn as a circle.

    img = io.BytesIO()
    plt.savefig(img, format='png', bbox_inches='tight')
    plt.close(fig)  # Close the figure to free memory
    img.seek(0)
    return base64.b64encode(img.getvalue()).decode()

# Define route for displaying the company distribution chart
@app.route('/company_distribution')
def company_distribution():
    plot_url = generate_company_chart()
    if plot_url is None:
        return render_template('company_distribution_chart.html', plot_url=None, message="No company distribution data available.")
    return render_template('company_distribution_chart.html', plot_url=plot_url, message=None)


# Extracted function for getting and plotting product distribution data
def generate_product_chart():
    # Fetch product distribution data from the database
    mycursor.execute("SELECT product, COUNT(*) FROM user_details GROUP BY product")
    product_data = mycursor.fetchall()

    # Check if there is product data to plot
    if not product_data:
        return None

    products = [product[0] for product in product_data]
    counts = [product[1] for product in product_data]

    # Plotting the product distribution pie chart
    fig, ax = plt.subplots()
    ax.pie(counts, labels=products, autopct='%1.1f%%', startangle=90)
    ax.axis('equal')  # Equal aspect ratio ensures that pie is drawn as a circle.

    img = io.BytesIO()
    plt.savefig(img, format='png', bbox_inches='tight')
    plt.close(fig)  # Close the figure to free memory
    img.seek(0)
    return base64.b64encode(img.getvalue()).decode()

# Define route for displaying the product distribution chart
@app.route('/product_distribution')
def product_distribution():
    plot_url = generate_product_chart()
    if plot_url is None:
        return render_template('product_distribution_chart.html', plot_url=None, message="No product distribution data available.")
    return render_template('product_distribution_chart.html', plot_url=plot_url, message=None)

if __name__ == "__main__":
    app.run(debug=True)
