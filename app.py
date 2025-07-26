from flask import Flask, render_template, request, redirect, url_for, session, flash
import sqlite3
import os
from werkzeug.utils import secure_filename
from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.secret_key = "your_secret_key"

UPLOAD_FOLDER = 'static/profile_pics'
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg'}
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

#Sqlite3 Database
def init_db():
    conn = sqlite3.connect("attendance.db")
    cursor = conn.cursor()

    cursor.execute('''CREATE TABLE IF NOT EXISTS users (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        username TEXT NOT NULL UNIQUE,
                        email TEXT NOT NULL UNIQUE,
                        password TEXT NOT NULL,
                        role TEXT DEFAULT "user",
                        profile_pic TEXT
                      )''')

    cursor.execute('''CREATE TABLE IF NOT EXISTS attendance (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        user_id INTEGER,
                        date TEXT,
                        status TEXT,
                        time TEXT,
                        FOREIGN KEY (user_id) REFERENCES users (id)
                      )''')

    cursor.execute('''CREATE TABLE IF NOT EXISTS leave_requests (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        user_id INTEGER,
                        date TEXT,
                        reason TEXT,
                        status TEXT DEFAULT "pending",
                        FOREIGN KEY (user_id) REFERENCES users (id)
                      )''')

    cursor.execute('''CREATE TABLE IF NOT EXISTS grades (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        days_attended INTEGER,
                        grade TEXT
                      )''')

    def add_time_column():
        cursor.execute("PRAGMA table_info(attendance);")
        columns = cursor.fetchall()
        if 'time' not in [c[1] for c in columns]:
            cursor.execute("ALTER TABLE attendance ADD COLUMN time TEXT;")
            conn.commit()
    add_time_column()

    conn.commit()
    conn.close()

init_db()

@app.route('/')
def home():
    return redirect(url_for('login'))    #login Route

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        with sqlite3.connect("attendance.db") as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM users WHERE username = ?", (username,))
            user = cursor.fetchone()
            if user and check_password_hash(user[3], password):
                session['user_id'] = user[0]
                session['username'] = user[1]
                session['role'] = user[4]
                return redirect(url_for('admin_dashboard' if user[4] == 'admin' else 'user_dashboard'))
            flash("Invalid credentials")
    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])   #Registration Route
def register():
    if request.method == 'POST':
        username = request.form['username']
        email = request.form['email']
        password = generate_password_hash(request.form['password'])
        with sqlite3.connect("attendance.db") as conn:
            cursor = conn.cursor()
            try:
                cursor.execute("INSERT INTO users (username, email, password) VALUES (?, ?, ?)", (username, email, password))
                conn.commit()
                flash("Registration successful!")
                return redirect(url_for('login'))
            except sqlite3.IntegrityError:
                flash("Username or Email already exists.")
    return render_template('register.html')

@app.route('/user_dashboard')       #User Dasboard Router
def user_dashboard():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    return render_template('user_dashboard.html', username=session['username'])

@app.route('/mark_attendance', methods=['POST'])     #Mark Attendance
def mark_attendance():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    user_id = session['user_id']
    today = datetime.now().date().isoformat()
    now = datetime.now().strftime("%H:%M:%S")
    with sqlite3.connect("attendance.db") as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM attendance WHERE user_id = ? AND date = ?", (user_id, today))
        if not cursor.fetchone():
            cursor.execute("INSERT INTO attendance (user_id, date, status, time) VALUES (?, ?, 'present', ?)", (user_id, today, now))
            conn.commit()
            flash("Attendance marked at " + now)
        else:
            flash("Already marked")
    return redirect(url_for('user_dashboard'))

@app.route('/leave_request', methods=['POST'])       #leave request
def leave_request():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    with sqlite3.connect("attendance.db") as conn:
        cursor = conn.cursor()
        cursor.execute("INSERT INTO leave_requests (user_id, date, reason) VALUES (?, ?, ?)",
                       (session['user_id'], request.form['date'], request.form['reason']))
        conn.commit()
        flash("Leave requested")
    return redirect(url_for('user_dashboard'))

@app.route('/edit_profile', methods=['GET', 'POST'])    #Edit profile
def edit_profile():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    user_id = session['user_id']
    if request.method == 'POST':
        username = request.form['username']
        email = request.form['email']
        profile_pic = request.files.get('profile_pic')
        pic_path = None
        if profile_pic and allowed_file(profile_pic.filename):
            filename = secure_filename(profile_pic.filename)
            file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            profile_pic.save(file_path)
            pic_path = f"/{app.config['UPLOAD_FOLDER']}/{filename}"
        with sqlite3.connect("attendance.db") as conn:
            cursor = conn.cursor()
            cursor.execute("UPDATE users SET username=?, email=?, profile_pic=? WHERE id=?",
                           (username, email, pic_path, user_id))
            conn.commit()
            flash("Updated")
        return redirect(url_for('user_dashboard'))
    with sqlite3.connect("attendance.db") as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT username, email, profile_pic FROM users WHERE id=?", (user_id,))
        return render_template('edit_profile.html', user=cursor.fetchone())

# Here start Admin Dasboard Code
@app.route('/admin_dashboard')                             
def admin_dashboard():
    if 'user_id' not in session or session['role'] != 'admin':
        return redirect(url_for('login'))
    with sqlite3.connect("attendance.db") as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM users WHERE role='user'")
        users = cursor.fetchall()                                          #Leave request
        cursor.execute("SELECT leave_requests.id, users.username, leave_requests.date, leave_requests.reason, leave_requests.status FROM leave_requests JOIN users ON leave_requests.user_id = users.id")
        leave_requests = cursor.fetchall()
    return render_template("admin_dashboard.html", users=users, leave_requests=leave_requests)

@app.route('/approve_leave/<int:leave_id>')    #Approve Leave
def approve_leave(leave_id):
    if 'user_id' not in session or session['role'] != 'admin':
        return redirect(url_for('login'))
    with sqlite3.connect("attendance.db") as conn:
        cursor = conn.cursor()
        cursor.execute("UPDATE leave_requests SET status='approved' WHERE id=?", (leave_id,))
        conn.commit()
    flash("Leave approved")
    return redirect(url_for('admin_dashboard'))

@app.route('/reject_leave/<int:leave_id>')    #reject leave
def reject_leave(leave_id):
    if 'user_id' not in session or session['role'] != 'admin':
        return redirect(url_for('login'))
    with sqlite3.connect("attendance.db") as conn:
        cursor = conn.cursor()
        cursor.execute("UPDATE leave_requests SET status='rejected' WHERE id=?", (leave_id,))
        conn.commit()
    flash("Leave rejected")
    return redirect(url_for('admin_dashboard'))

@app.route('/view_attendance/<int:user_id>')        #view attendance
def view_attendance(user_id):
    with sqlite3.connect("attendance.db") as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT date, status, time FROM attendance WHERE user_id=?", (user_id,))
        return render_template('report.html', records=cursor.fetchall())

# ✨ Admin Features Extension Below
@app.route('/admin/add_attendance', methods=['POST'])
def add_attendance():
    if 'user_id' not in session or session['role'] != 'admin': return redirect(url_for('login'))
    user_id, date, status, time = request.form['user_id'], request.form['date'], request.form['status'], request.form['time']
    with sqlite3.connect("attendance.db") as conn:
        cursor = conn.cursor()
        cursor.execute("INSERT INTO attendance (user_id, date, status, time) VALUES (?, ?, ?, ?)", (user_id, date, status, time))
        conn.commit()
        flash("Attendance added")
    return redirect(url_for('admin_dashboard'))

    #Edit Attendance
@app.route('/edit_attendance/<int:user_id>', methods=['GET', 'POST'])
def edit_attendance(user_id):
    if 'user_id' not in session or session['role'] != 'admin':
        return redirect(url_for('login'))

    with sqlite3.connect("attendance.db") as conn:
        cursor = conn.cursor()

        if request.method == 'POST':
            attendance_id = request.form['attendance_id']
            new_status = request.form['status']
            cursor.execute("UPDATE attendance SET status = ? WHERE id = ?", (new_status, attendance_id))
            conn.commit()
            flash("Attendance updated.")
            return redirect(url_for('edit_attendance', user_id=user_id))

        cursor.execute("SELECT id, date, status, time FROM attendance WHERE user_id = ?", (user_id,))
        records = cursor.fetchall()

    return render_template('edit_attendance.html', records=records, user_id=user_id)


@app.route('/delete_user/<int:user_id>')
def delete_user(user_id):
    if 'user_id' not in session or session['role'] != 'admin':
        return redirect(url_for('login'))

    with sqlite3.connect("attendance.db") as conn:
        cursor = conn.cursor()
        # First delete attendance and leave records for the user
        cursor.execute("DELETE FROM attendance WHERE user_id=?", (user_id,))
        cursor.execute("DELETE FROM leave_requests WHERE user_id=?", (user_id,))
        # Then delete the user
        cursor.execute("DELETE FROM users WHERE id=?", (user_id,))
        conn.commit()
    flash("User deleted successfully.")
    return redirect(url_for('admin_dashboard'))


@app.route('/admin/user_report', methods=['GET', 'POST'])     #user report
def user_report():
    if 'user_id' not in session or session['role'] != 'admin': return redirect(url_for('login'))
    records, username = [], ""
    if request.method == 'POST':
        uid, from_date, to_date = request.form['user_id'], request.form['from_date'], request.form['to_date']
        with sqlite3.connect("attendance.db") as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT username FROM users WHERE id=?", (uid,))
            username = cursor.fetchone()[0]
            cursor.execute("SELECT date, status, time FROM attendance WHERE user_id=? AND date BETWEEN ? AND ?", (uid, from_date, to_date))
            records = cursor.fetchall()
    return render_template("user_report.html", records=records, username=username)

@app.route('/admin/system_report', methods=['GET', 'POST'])         #System Report
def system_report():
    if 'user_id' not in session or session['role'] != 'admin': return redirect(url_for('login'))
    records = []
    if request.method == 'POST':
        f, t = request.form['from_date'], request.form['to_date']
        with sqlite3.connect("attendance.db") as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT users.username, attendance.date, attendance.status, attendance.time FROM attendance JOIN users ON attendance.user_id = users.id WHERE date BETWEEN ? AND ?", (f, t))
            records = cursor.fetchall()
    return render_template("system_report.html", records=records)

@app.route('/admin/assign_grades')    #assign Grades
def assign_grades():
    if 'user_id' not in session or session['role'] != 'admin': return redirect(url_for('login'))
    def calc(p): return 'A' if p>=26 else 'B' if p>=20 else 'C' if p>=15 else 'D' if p>=10 else 'F'
    with sqlite3.connect("attendance.db") as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM grades")
        cursor.execute("SELECT user_id, COUNT(*) FROM attendance WHERE status='present' GROUP BY user_id")
        for uid, count in cursor.fetchall():
            cursor.execute("INSERT INTO grades (days_attended, grade) VALUES (?, ?)", (count, calc(count)))
        conn.commit()
        flash("Grades updated")
    return redirect(url_for('admin_dashboard'))

#update grades by hand
@app.route('/admin/update_grades', methods=['POST'])  
def update_grades():
    if 'user_id' not in session or session['role'] != 'admin':
        return redirect(url_for('login'))

    # Get grade thresholds from the form
    grade_a = int(request.form['grade_a'])
    grade_b = int(request.form['grade_b'])
    grade_c = int(request.form['grade_c'])

    # Save thresholds in session or globally (in memory only)
    session['grade_a'] = grade_a
    session['grade_b'] = grade_b
    session['grade_c'] = grade_c

    # Define grading logic using new values
    def calculate_grade(present):
        if present >= grade_a:
            return 'A'
        elif present >= grade_b:
            return 'B'
        elif present >= grade_c:
            return 'C'
        elif present >= 10:
            return 'D'
        else:
            return 'F'

    with sqlite3.connect("attendance.db") as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM grades")  # Clear previous
        cursor.execute("SELECT user_id, COUNT(*) FROM attendance WHERE status='present' GROUP BY user_id")
        data = cursor.fetchall()
        for user_id, present in data:
            grade = calculate_grade(present)
            cursor.execute("INSERT INTO grades (days_attended, grade) VALUES (?, ?)", (present, grade))
        conn.commit()

    flash("🎯 Grading system updated and grades assigned!")
    return redirect(url_for('admin_dashboard'))



# Promote a user to admin(I use this step to see just dmin dashboard.This is a temporary step not use this method. You need to remove this code)
@app.route('/make_admin/<username>')
def make_admin(username):
    with sqlite3.connect("attendance.db") as conn:
        cursor = conn.cursor()
        cursor.execute("UPDATE users SET role = 'admin' WHERE username = ?", (username,))
        conn.commit()
    return f"User '{username}' has been promoted to admin."

@app.route('/logout')
def logout():
    session.clear()
    flash("Logged out")
    return redirect(url_for('login'))

if __name__ == '__main__':
    app.run(debug=True)
