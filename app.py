from flask import Flask, render_template, request, redirect, url_for, session, flash
import sqlite3
import os
import matplotlib.pyplot as plt
import numpy as np
import plotly.express as px
import pandas as pd
import base64
import io
from urllib.parse import urlencode
from threading import Thread


app = Flask(__name__)
app.secret_key = "your_secret_key"

DATABASE = 'grades.db'


def connect_db():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn


def create_tables():
    conn = connect_db()
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL,
            password TEXT NOT NULL
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS subjects (
            subject_id INTEGER PRIMARY KEY AUTOINCREMENT,
            subject_name VARCHAR NOT NULL,
            user_id INTEGER NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users (id),
            UNIQUE (subject_id, user_id)
        )
    """)


    c.execute("""
        CREATE TABLE IF NOT EXISTS grades (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            subject VARCHAR(255) NOT NULL,
            assessment_name VARCHAR(255) NOT NULL,
            score FLOAT NOT NULL,
            total_score FLOAT NOT NULL,
            weight FLOAT NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users (id)
        )
    """)
    conn.commit()
    conn.close()

def retrieve_grades(subjectname):
    conn = connect_db()
    c = conn.cursor()
    c.execute("SELECT * FROM grades WHERE subject = ?", (subjectname,))
    grades = c.fetchall()
    conn.close()
    return grades

if __name__ == '__main__':
    create_tables()

@app.route('/')
def index():
    if 'username' in session:
        return redirect(url_for('dashboard'))
    return render_template('index.html')


@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']

        with connect_db() as conn:
            c = conn.cursor()
            c.execute("SELECT * FROM users WHERE username=?", (username,))
            user = c.fetchone()

            if user is not None:
                flash('Username already exists. Please choose a different username.', 'error')
                return redirect(url_for('signup'))

            c.execute("INSERT INTO users (username, password) VALUES (?, ?)", (username, password))
            conn.commit()

        flash('Account created successfully. Please login.', 'success')
        return redirect(url_for('login'))

    return render_template('signup.html')


@app.route('/about')
def about():
    return render_template('about.html')


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']

        with connect_db() as conn:
            c = conn.cursor()
            c.execute("SELECT * FROM users WHERE username=? AND password=?", (username, password))
            user = c.fetchone()

            if user is None:
                flash('Invalid username or password. Please try again.', 'error')
                return redirect(url_for('login'))

            session['username'] = username
            session['user_id'] = user['id']

        flash('Login successful!', 'success')
        return redirect(url_for('subjectdashboard'))

    return render_template('login.html')
    

@app.route('/logout')
def logout():
    session.pop('username', None)
    session.pop('user_id', None)
    return redirect(url_for('index'))


@app.route('/subjectdashboard', methods=['GET', 'POST'])
def subjectdashboard():
    if 'username' not in session:
        return redirect(url_for('login'))

    if 'subjects' not in session:
        session['subjects'] = []

    if request.method == 'POST':
        subject = request.form.get('subject')

        if subject and subject != 'custom':
            conn = connect_db()
            c = conn.cursor()
            c.execute("INSERT INTO subjects (subject_name, user_id) VALUES (?, ?)",
                      (subject, session['user_id']))
            conn.commit()
            conn.close()

            session['subjects'].append(subject)
            flash('Subject added successfully!', 'success')

            return redirect(url_for('dashboard', subjectname=subject.upper()))

    return render_template('subjectdashboard.html', username=session['username'], subjects=session['subjects'])

def calculate_final_grade(grades, percentage_goal=100):
    total_score = 0
    total_possible_score = 0

    for grade in grades:
        try:
            score = int(grade[3])  
            possible_score = int(grade[4])  
            total_score += score
            total_possible_score += possible_score
        except ValueError:
            continue


    if total_possible_score == 0:
        final_grade = 0
    else:
        final_grade = (total_score / total_possible_score) * percentage_goal

    return final_grade


@app.route('/dashboard', methods=['GET', 'POST'])
def dashboard():
    if 'username' not in session:
        return redirect(url_for('login'))

    subject_name = request.args.get('subjectname', None)
    grades = retrieve_grades(subject_name)

    if request.method == 'POST':
        if 'percentage_goal' in request.form:
            percentage_goal = int(request.form['percentage_goal'])

            session['percentage_goal'] = percentage_goal

            flash('Percentage goal set successfully!', 'success')
        else:
            assessment_names = request.form.getlist('assessment_name[]')
            for i in range(len(assessment_names)):
                assessment_name = assessment_names[i]
                score = int(request.form[f'assessment_score_{i+1}'])
                total_score = int(request.form[f'assessment_total_{i+1}'])
                weight = int(request.form[f'assessment_weight_{i+1}'])

                conn = connect_db()
                c = conn.cursor()
                c.execute("INSERT INTO grades (user_id, subject, assessment_name, score, total_score, weight) VALUES (?, ?, ?, ?, ?, ?)",
                          (session['user_id'], subject_name, assessment_name, score, total_score, weight))
                conn.commit()
                conn.close()

            flash('Grades added successfully!', 'success')

        return redirect(url_for('dashboard', subjectname=subject_name))

    conn = connect_db()
    c = conn.cursor()
    c.execute("SELECT * FROM grades WHERE user_id=? AND subject=?", (session['user_id'], subject_name))
    grades_from_db = c.fetchall()
    conn.close()

   
    def calculate_final_grade(grades, percentage_goal=100):
        total_weighted_score = 0
        total_weight = 0

        for grade in grades:
            try:
                score = float(grade['score'])
                total_score = float(grade['total_score'])
                weight = float(grade['weight'])
                total_weighted_score += (score / total_score) * weight
                total_weight += weight
            except ValueError:
                continue

        if total_weight == 0:
            final_grade = 0
        else:
            final_grade = (total_weighted_score / total_weight) * percentage_goal

        return final_grade

    final_grade = calculate_final_grade(grades)
    graph_html = None

    def generate_graph_async():
        nonlocal graph_html
        graph_html = generate_graph(grades)

    graph_thread = Thread(target=generate_graph_async)
    graph_thread.start()
    graph_thread.join()

    return render_template('dashboard.html', subjectname=subject_name, username=session['username'], grades=grades,
                           final_grade=final_grade, graph_html=graph_html)

def generate_graph(grades):
    if grades:
        assessment_names = [grade['assessment_name'] for grade in grades]
        scores = [grade['score'] for grade in grades]

        x = np.arange(len(assessment_names))
        y = np.array(scores)

        fig, ax = plt.subplots()
        ax.bar(x, y)
        ax.set_xlabel('Assessments')
        ax.set_ylabel('Scores')
        ax.set_title('Grade Distribution')
        ax.set_xticks(x)
        ax.set_xticklabels(assessment_names)
        plt.tight_layout()

        image_buffer = io.BytesIO()
        plt.savefig(image_buffer, format='png')
        image_buffer.seek(0)

        encoded_image = base64.b64encode(image_buffer.read()).decode('utf-8')

        graph_html = f'<img src="data:image/png;base64,{encoded_image}" alt="Grade Graph">'

        return graph_html
    else:
        return None
    

@app.route('/report')
def report():
    if 'username' not in session:
        return redirect(url_for('login'))

    subject_name = request.args.get('subjectname')

    conn = connect_db()
    c = conn.cursor()
    c.execute("SELECT * FROM grades WHERE user_id=? AND subject=?", (session['user_id'], subject_name))
    grades = c.fetchall()
    conn.close()

    def calculate_final_grade(grades, percentage_goal=100):
        total_weighted_score = 0
        total_weight = 0

        for grade in grades:
            try:
                score = float(grade['score'])
                total_score = float(grade['total_score'])
                weight = float(grade['weight'])
                total_weighted_score += (score / total_score) * weight
                total_weight += weight
            except ValueError:
                continue

        if total_weight == 0:
            final_grade = 0
        else:
            final_grade = (total_weighted_score / total_weight) * percentage_goal

        return final_grade

    final_grade = calculate_final_grade(grades)
    graph_html = generate_graph(grades)

    return render_template('report.html', final_grade=final_grade, graph_html=graph_html, subjectname=subject_name, grades=grades)

@app.route('/delete/<int:grade_id>', methods=['POST'])
def delete_grade(grade_id):
    conn = connect_db()
    c = conn.cursor()
    c.execute("DELETE FROM grades WHERE id=?", (grade_id,))
    conn.commit()
    conn.close()

    flash('Grade deleted successfully!', 'success')
    return redirect(url_for('dashboard', subjectname=request.args.get('subjectname', None)))


if __name__ == '__main__':
    create_tables()
    app.run(debug=True)