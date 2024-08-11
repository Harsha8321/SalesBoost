from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
import logging
import os
import subprocess
from datetime import datetime
import pandas as pd
import joblib

app = Flask(__name__)
app.config['SECRET_KEY'] = '34880a530c25ecb0c9676e18f792e1e5'  # Replace with your secret key
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///users.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

# Set up logging
logging.basicConfig(level=logging.DEBUG)

UPLOAD_FOLDER = 'uploads'
ALLOWED_EXTENSIONS = {'csv'}

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

# Load the encoders and the model
encoders = joblib.load('./Website/static/encoders.pkl')
model = joblib.load('./Website/models/random_forest_model.pkl')

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(150), nullable=False)
    email = db.Column(db.String(150), unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=False)

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@app.route('/')
def home():
    return render_template('index.html')

@app.route('/register', methods=['POST'])
def register():
    name = request.form['name']
    email = request.form['email']
    password = request.form['password']

    user = User.query.filter_by(email=email).first()
    if user:
        flash('Email already registered!', 'error')
    else:
        hashed_password = generate_password_hash(password, method='pbkdf2:sha256')
        new_user = User(name=name, email=email, password=hashed_password)
        db.session.add(new_user)
        db.session.commit()
        flash('Registration successful!', 'success')
        logging.debug(f"Registered new user: {new_user}")

    return redirect(url_for('home'))

@app.route('/login', methods=['POST'])
def login():
    email = request.form['email']
    password = request.form['password']

    user = User.query.filter_by(email=email).first()
    if user:
        logging.debug(f"User found: {user}")
        if check_password_hash(user.password, password):
            flash(f'Welcome back, {user.name}!', 'success')
            logging.debug(f"Password matched for user: {user}")
            return redirect(url_for('dashboard'))  # Redirect to dashboard
        else:
            flash('Invalid email or password', 'error')
            logging.debug("Password did not match")
    else:
        flash('Invalid email or password', 'error')
        logging.debug("User not found")

    return redirect(url_for('home'))

@app.route('/dashboard')
def dashboard():
    return render_template('dashboard.html')

@app.route('/upload', methods=['POST'])
def upload_file():
    if 'file' not in request.files:
        return redirect(request.url)
    file = request.files['file']
    if file.filename == '':
        return redirect(request.url)
    if file and allowed_file(file.filename):
        filename = secure_filename(file.filename)
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(file_path)
        os.chdir('../../')
        # Call the Jupyter notebook to process the file and save graphs
        subprocess.run(["jupyter", "nbconvert", "--execute", "--to", "notebook", "--ExecutePreprocessor.timeout=600",
                        "./notebook.ipynb"])

        # Redirect to the new page displaying the graphs
        return render_template('graphs.html')
    flash('Invalid file type. Please upload a CSV file.', 'error')
    return redirect(url_for('dashboard'))

@app.route('/predict')
def predict():
    return render_template('predict.html')

@app.route('/predict_sales', methods=['POST'])
def predict_sales():
    try:
        now = datetime.now()
        real_time_data = pd.DataFrame({
            'DayOfWeek': [now.weekday()],
            'Month': [now.month],
            'Hour': [now.hour],
            'Branch': [request.form['Branch']],
            'City': [request.form['City']],
            'Customer type': [request.form['CustomerType']],
            'Gender': [request.form['Gender']],
            'Product line': [request.form['ProductLine']],
            'Unit price': [float(request.form['UnitPrice'])],
            'Quantity': [int(request.form['Quantity'])],
            'Payment': [request.form['Payment']]
        })

        # Encode categorical features
        for col in real_time_data.columns:
            if col in encoders:
                try:
                    real_time_data[col] = encoders[col].transform(real_time_data[col])
                except ValueError:
                    # Handle unseen category
                    unique_values = list(encoders[col].classes_)
                    unique_values.append(real_time_data[col].iloc[0])
                    encoders[col].fit(unique_values)
                    real_time_data[col] = encoders[col].transform(real_time_data[col])

        prediction = model.predict(real_time_data)
        formatted_prediction = f"{prediction[0]:.3f}"
        return jsonify({'prediction': formatted_prediction})

    except Exception as e:
        return jsonify({'error': str(e)})


if __name__ == '__main__':
    with app.app_context():
        db.create_all()  # This line creates the database tables
    app.run(debug=True)

