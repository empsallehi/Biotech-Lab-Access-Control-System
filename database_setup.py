import sqlite3
import random
from datetime import datetime, timedelta


def build_advanced_system():
    conn = sqlite3.connect("biotech_lab_access.db")
    cursor = conn.cursor()
    cursor.execute("DROP TABLE IF EXISTS employees")
    cursor.execute("DROP TABLE IF EXISTS access_logs")
    cursor.execute("""
    CREATE TABLE employees (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        national_id TEXT UNIQUE,
        personnel_code TEXT,
        full_name TEXT,
        role TEXT,
        card_uid TEXT,
        pin_code TEXT,
        failed_attempts INTEGER DEFAULT 0,
        is_active INTEGER DEFAULT 1
    )""")
    cursor.execute("""
    CREATE TABLE access_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        card_uid TEXT,
        employee_name TEXT,
        timestamp TEXT,
        gate_name TEXT,
        status TEXT
    )""")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_timestamp ON access_logs(timestamp);")

    staff_list = [
        ('1112223334', '980101', 'Khatere Salehi', 'Lab Manager', '01020304', '0843'),
        ('2223334445', '980102', 'Dr. Mehrdad Babaie', 'Senior Geneticist', '11223344', '0161'),
        ('3334445556', '980103', 'Maryam Amiri', 'Cell Culture Tech', '55667788', '7788'),
        ('4444556667', '980104', 'Ali Davoudi', 'Intern', 'AABBCCDD', '9636'),
        ('5556667778', '980105', 'Dr. Sara Mahdavi', 'Bioinformatician', 'C0FFEE99', '1122')
    ]
    for emp in staff_list:
        cursor.execute("""
            INSERT INTO employees (national_id, personnel_code, full_name, role, card_uid, pin_code)
            VALUES (?, ?, ?, ?, ?, ?)
        """, emp)

    # Seed one blocked employee for testing
    cursor.execute("UPDATE employees SET is_active = 0 WHERE full_name = 'Ali Davoudi'")
    conn.commit()

    print("Generating comprehensive records for analytical charts...")

    end_date   = datetime(2026, 6, 26)   # today (Friday)
    start_date = end_date - timedelta(days=90)
    delta_days = (end_date - start_date).days

    gates = ["Biotech Lab Main Gate", "Genetics Cleanroom", "Bioinformatics Unit"]

    # Hourly weights for a regular workday: entry peak 7:30-9, lunch 12-13, exit peak 16:30-18:30
    workday_hours = {
        7: 5, 8: 20, 9: 14, 10: 6, 11: 4,
        12: 9, 13: 8,
        14: 5, 15: 6, 16: 8, 17: 16, 18: 10, 19: 4, 20: 1
    }

    # Hourly weights for Thursday (half day): entry peak 8-9, early exit 14-15
    thursday_hours = {
        8: 10, 9: 12, 10: 8, 11: 5,
        12: 6, 13: 5,
        14: 10, 15: 8, 16: 4
    }

    # Hourly weights for Friday (day off): only managers/seniors, limited hours
    friday_hours = {9: 3, 10: 4, 11: 3, 14: 2, 15: 2}

    def pick_hour(weights):
        return random.choices(list(weights.keys()), weights=list(weights.values()), k=1)[0]

    # Status ratios per day type
    workday_statuses  = ["ALLOWED"] * 14 + ["DENIED_PIN"] * 2 + ["UNKNOWN_CARD"] * 1
    thursday_statuses = ["ALLOWED"] * 12 + ["DENIED_PIN"] * 2 + ["UNKNOWN_CARD"] * 1
    friday_statuses   = ["ALLOWED"] * 9  + ["DENIED_PIN"] * 1

    all_cards      = ['01020304', '11223344', '55667788', 'AABBCCDD', 'C0FFEE99', '99887766']
    thursday_cards = ['01020304', '11223344', '55667788', 'C0FFEE99']  # no intern, no unknown card
    friday_cards   = ['01020304', '11223344', 'C0FFEE99']              # managers/seniors only

    logs_batch = []
    for d in range(delta_days + 1):
        curr_date = start_date + timedelta(days=d)
        weekday   = curr_date.weekday()  # 0=Mon ... 4=Fri, 5=Sat, 6=Sun

        if weekday == 4:      # Friday - day off
            scans    = random.randint(2, 5)
            cards    = friday_cards
            statuses = friday_statuses
            hw       = friday_hours

        elif weekday == 3:    # Thursday - half day
            scans    = random.randint(12, 22)
            cards    = thursday_cards
            statuses = thursday_statuses
            hw       = thursday_hours

        else:                 # Saturday-Wednesday - full workday
            scans    = random.randint(40, 65)
            cards    = all_cards
            statuses = workday_statuses
            hw       = workday_hours

        for _ in range(scans):
            card      = random.choice(cards)
            hour      = pick_hour(hw)
            minute    = random.randint(0, 59)
            second    = random.randint(0, 59)
            fake_time = curr_date.replace(hour=hour, minute=minute, second=second).strftime("%Y-%m-%d %H:%M:%S")

            cursor.execute("SELECT full_name, is_active FROM employees WHERE card_uid=?", (card,))
            emp_status = cursor.fetchone()
            if emp_status:
                name   = emp_status[0]
                status = random.choice(statuses) if emp_status[1] == 1 else "BLOCKED_CARD"
            else:
                name   = "Unauthorized Unknown"
                status = "UNKNOWN_CARD"

            logs_batch.append((card, name, fake_time, random.choice(gates), status))

    cursor.executemany(
        "INSERT INTO access_logs (card_uid, employee_name, timestamp, gate_name, status) VALUES (?,?,?,?,?)",
        logs_batch
    )
    conn.commit()
    conn.close()
    print("Database built successfully!")


if __name__ == "__main__":
    build_advanced_system()