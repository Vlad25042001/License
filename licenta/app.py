from flask import Flask, render_template, request, redirect, url_for, flash, session
import mariadb
import threading
import time
import re
from pirc522 import RFID
from config import Config
from RPLCD.i2c import CharLCD

app = Flask(__name__)
app.secret_key = 'your_secret_key'

# LCD Configuration
lcd = CharLCD('PCF8574', 0x27)  # I2C address of the LCD

# Function to center text on the LCD
def center_text(text, width=16):
    if len(text) > width:
        text is=text[:width]
    spaces = (width - len(text)) // 2
    return ' ' * spaces + text

# Function to format and center text on a 2x16 LCD
def format_lcd_text(line1, line2='', width=16):
    if len(line1) > width:
        line1 = line1[:width]
    if len(line2) > width:
        line2 = line2[:width]
    
    line1 = center_text(line1, width)
    line2 = center_text(line2, width)
    
    return line1, line2

# Database configuration
def connect_to_db():
    return mariadb.connect(
        user=Config.DB_USER,
        password=Config.DB_PASSWORD,
        host=Config.DB_HOST,
        port=Config.DB_PORT,
        database=Config.DB_NAME
    )

# Read RFID UID
def read_rfid_uid():
    rdr = RFID(pin_rst=22)
    try:
        while True:
            rdr.init()
            (error, data) = rdr.request()
            if not error:
                (error, uid) = rdr.anticoll()
                if not error:
                    rfid_uid = "".join(map(str, uid))
                    print(f"RFID UID: {rfid_uid}")
                    lcd.clear()
                    line1, line2 = format_lcd_text("RFID UID:", rfid_uid)
                    lcd.write_string(line1)
                    lcd.crlf()
                    lcd.write_string(line2)
                    rdr.cleanup()
                    return rfid_uid
            time.sleep(0.1)
    except Exception as e:
        print(f"Error: {e}")
        lcd.clear()
        line1, line2 = format_lcd_text("Error:", str(e))
        lcd.write_string(line1)
        lcd.crlf()
        lcd.write_string(line2)
    finally:
        rdr.cleanup()

# Detect presence with ultrasonic sensor
def detect_presence():
    try:
        with open('/tmp/sensor_status.txt', 'r') as file:
            status = file.read().strip()
        if status == "detected":
            print("Participant detected")
            lcd.clear()
            line1, line2 = format_lcd_text("Detected")
            lcd.write_string(line1)
            lcd.crlf()
            lcd.write_string(line2)
        return status == "detected"
    except Exception as e:
        print(f"Error reading sensor status: {e}")
        return False

# Notification and RFID UID assignment in terminal
def assign_rfid_uid(username):
    print(f"Assigning RFID UID for user: {username}")
    lcd.clear()
    line1, line2 = format_lcd_text("Assigning UID", username)
    lcd.write_string(line1)
    lcd.crlf()
    lcd.write_string(line2)
    rfid_uid = read_rfid_uid()
    if rfid_uid:
        conn = connect_to_db()
        cursor = conn.cursor()
        
        # Check if the UID already exists
        cursor.execute("SELECT username FROM participants WHERE rfid_uid = ?", (rfid_uid,))
        existing_user = cursor.fetchone()
        
        if existing_user:
            # Delete existing users with this UID
            cursor.execute("DELETE FROM participants WHERE rfid_uid = ?", (rfid_uid,))
            conn.commit()
            print(f"Deleted existing user(s) with UID: {rfid_uid}")
        
        # Update current user with the new UID
        sql = "UPDATE participants SET rfid_uid = ? WHERE username = ?"
        cursor.execute(sql, (rfid_uid, username))
        conn.commit()
        cursor.close()
        conn.close()
        print(f"RFID UID {rfid_uid} assigned to {username}")
        lcd.clear()
        line1, line2 = format_lcd_text("UID assigned", rfid_uid)
        lcd.write_string(line1)
        lcd.crlf()
        lcd.write_string(line2)
        time.sleep(5)  # Display the message for a few seconds
        lcd.clear()

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        name = request.form['name']
        surname = request.form['surname']
        cnp = request.form['cnp']
        id_card = request.form['id_card']
        phone = request.form['phone']
        email = request.form['email'].lower()  # Normalize email to lowercase
        username = request.form['username']
        password = request.form['password']
        address = request.form['address']
        city = request.form['city']
        county = request.form['county']

        # Field validation
        if len(cnp) != 13 or not cnp.isdigit():
            flash('CNP must have 13 digits.', 'danger')
            return redirect(url_for('register'))
        if not phone.isdigit() or len(phone) != 10:
            flash('Phone number must have 10 digits.', 'danger')
            return redirect(url_for('register'))
        if not re.match(r"[^@]+@[^@]+\.[^@]+", email):
            flash('Invalid email address.', 'danger')
            return redirect(url_for('register'))

        conn = connect_to_db()
        cursor = conn.cursor()

        # Check if CNP, phone, email, ID card or username already exist
        cursor.execute("SELECT * FROM participants WHERE cnp = ? OR phone = ? OR LOWER(email) = LOWER(?) OR id_card = ? OR username = ?", (cnp, phone, email, id_card, username))
        existing_user = cursor.fetchone()
        if existing_user:
            print("Duplicate entry detected: ", existing_user)
            flash('CNP, phone, email, ID card, or username already exists in the system.', 'danger')
            return redirect(url_for('register'))

        sql = "INSERT INTO participants (name, surname, cnp, id_card, phone, email, username, password, address, city, county, rfid_uid) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, '')"
        cursor.execute(sql, (name, surname, cnp, id_card, phone, email, username, password, address, city, county))
        conn.commit()
        cursor.close()
        conn.close()
        
        flash('Participant registered successfully! Please assign an RFID UID.', 'success')
        threading.Thread(target=assign_rfid_uid, args=(username,)).start()  # Start thread to assign RFID UID
        return redirect(url_for('index'))
    
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        
        conn = connect_to_db()
        cursor = conn.cursor()
        sql = "SELECT * FROM participants WHERE username = ? AND password = ?"
        cursor.execute(sql, (username, password))
        result = cursor.fetchone()
        cursor.close()
        conn.close()
        
        if result:
            session['username'] = username
            print(f"Login successful for user: {username}")
            flash('Login successful! Please scan your RFID tag.', 'success')
            lcd.clear()
            line1, line2 = format_lcd_text("Login success", username)
            lcd.write_string(line1)
            lcd.crlf()
            lcd.write_string(line2)
            return redirect(url_for('verify_rfid'))
        else:
            print(f"Login failed for user: {username}")
            flash('Invalid username or password.', 'danger')
            lcd.clear()
            line1, line2 = format_lcd_text("Login failed", username)
            lcd.write_string(line1)
            lcd.crlf()
            lcd.write_string(line2)
            return redirect(url_for('login'))  # Redirecționăm utilizatorul înapoi la pagina de login pentru a afișa mesajul de eroare
    
    return render_template('login.html')

@app.route('/verify_rfid', methods=['GET', 'POST'])
def verify_rfid():
    if 'username' not in session:
        print("Attempt to access verify_rfid without logging in.")
        flash('You must be logged in to verify your RFID tag.', 'danger')
        lcd.clear()
        line1, line2 = format_lcd_text("Login req")
        lcd.write_string(line1)
        lcd.crlf()
        lcd.write_string(line2)
        return redirect(url_for('login'))
    
    username = session['username']
    print(f"User {username} is verifying RFID UID.")
    flash('Please scan your RFID tag.', 'info')
    lcd.clear()
    line1, line2 = format_lcd_text("Scan RFID", username)
    lcd.write_string(line1)
    lcd.crlf()
    lcd.write_string(line2)
    
    if request.method == 'POST':
        if detect_presence():
            rfid_uid = read_rfid_uid()
            print(f"RFID UID scanned: {rfid_uid}")
            
            conn = connect_to_db()
            cursor = conn.cursor()
            sql = "SELECT * FROM participants WHERE username = ? AND rfid_uid = ?"
            cursor.execute(sql, (username, rfid_uid))
            result = cursor.fetchone()
            cursor.close()
            conn.close()
            
            if result:
                print(f"RFID verification successful for user: {username}")
                flash('RFID verification successful! You are allowed to enter.', 'success')
                lcd.clear()
                line1, line2 = format_lcd_text("Access granted", username)
                lcd.write_string(line1)
                lcd.crlf()
                lcd.write_string(line2)
                with open('/tmp/servo_status.txt', 'w') as file:
                    file.write('open')
                time.sleep(5)  # Display the message for a few seconds
                lcd.clear()
                return redirect(url_for('index'))
            else:
                print(f"RFID verification failed for user: {username}. RFID UID: {rfid_uid}")
                flash('RFID UID does not match. Access denied.', 'danger')
                lcd.clear()
                line1, line2 = format_lcd_text("Access denied", username)
                lcd.write_string(line1)
                lcd.crlf()
                lcd.write_string(line2)
                with open('/tmp/servo_status.txt', 'w') as file:
                    file.write('close')
        else:
            print("No presence detected.")
            flash('No presence detected. Access denied.', 'danger')
            lcd.clear()
            line1, line2 = format_lcd_text("No presence", "detected")
            lcd.write_string(line1)
            lcd.crlf()
            lcd.write_string(line2)
    
    return render_template('verify_rfid.html')

if __name__ == '__main__':
    app.run(debug=True, port=5000)
