import sqlite3
from datetime import datetime, timedelta
from flask import Flask, render_template, request, jsonify

app = Flask(__name__)
DB_NAME = "biotech_lab_access.db"


# Helpers
def get_db():
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    return conn


# Main dashboard page
@app.route('/')
def index():
    conn = get_db()
    cur = conn.cursor()

    # Last 50 access logs, joined with employee role
    cur.execute("""
        SELECT al.id, al.card_uid, al.employee_name, al.timestamp, al.gate_name, al.status,
               e.role
        FROM access_logs al
        LEFT JOIN employees e ON e.card_uid = al.card_uid
        ORDER BY al.id DESC LIMIT 50
    """)
    logs = cur.fetchall()

    # Employees whose badge is currently blocked, with their last log status
    cur.execute("""
        SELECT e.card_uid, e.full_name, e.role,
               (SELECT al2.status FROM access_logs al2
                WHERE al2.card_uid = e.card_uid
                ORDER BY al2.id DESC LIMIT 1) AS last_status
        FROM employees e
        WHERE e.is_active = 0
        ORDER BY e.full_name
    """)
    blocked_employees = cur.fetchall()

    # Full employee list, for the "Manage Employees" panel
    cur.execute("""
        SELECT id, national_id, personnel_code, full_name, role, card_uid, pin_code, is_active
        FROM employees ORDER BY full_name
    """)
    all_employees = cur.fetchall()

    # Overall access stats
    cur.execute("SELECT COUNT(*) FROM access_logs")
    total_count = cur.fetchone()[0] or 1
    cur.execute("SELECT COUNT(*) FROM access_logs WHERE status='ALLOWED'")
    allowed_count = cur.fetchone()[0] or 0
    denied_count = total_count - allowed_count

    # Busiest hour overall
    cur.execute("""
        SELECT STRFTIME('%H', timestamp) AS hr, COUNT(*) AS cnt
        FROM access_logs GROUP BY hr ORDER BY cnt DESC LIMIT 1
    """)
    ph_row = cur.fetchone()
    peak_hour = int(ph_row['hr']) if ph_row else 0

    failure_rate = round((denied_count / total_count) * 100, 1)
    success_rate = round((allowed_count / total_count) * 100, 1)

    # Card involved in the most block/lock events (security summary)
    cur.execute("""
        SELECT al.employee_name, COUNT(*) AS cnt
        FROM access_logs al
        WHERE al.status IN ('BLOCKED_CARD','CARD_LOCKED')
        GROUP BY al.card_uid ORDER BY cnt DESC LIMIT 1
    """)
    ba_row = cur.fetchone()
    blocked_analysis = (ba_row['employee_name'], ba_row['cnt']) if ba_row else None

    conn.close()

    return render_template(
        "dashboard.html",
        logs=logs,
        blocked_employees=blocked_employees,
        all_employees=all_employees,
        total_count=total_count,
        allowed_count=allowed_count,
        denied_count=denied_count,
        peak_hour=peak_hour,
        failure_rate=failure_rate,
        success_rate=success_rate,
        blocked_analysis=blocked_analysis,
    )


# GET /api/stats — polled by the dashboard every 8s
@app.route('/api/stats')
def api_stats():
    time_range = request.args.get('range', '7d')
    conn = get_db()
    cur = conn.cursor()

    # Resolve the requested time range to a "since" timestamp
    now = datetime.now()
    range_map = {
        '24h': now - timedelta(hours=24),
        '7d':  now - timedelta(days=7),
        '30d': now - timedelta(days=30),
        '90d': now - timedelta(days=90),
    }
    since = range_map.get(time_range)  # None = all time

    if since:
        since_str = since.strftime('%Y-%m-%d %H:%M:%S')
        where = "WHERE timestamp >= ?"
        params = (since_str,)
    else:
        where = ""
        params = ()

    # Totals for the selected range
    cur.execute(f"SELECT COUNT(*) FROM access_logs {where}", params)
    total = cur.fetchone()[0] or 1
    cur.execute(f"SELECT COUNT(*) FROM access_logs {where} {'AND' if where else 'WHERE'} status='ALLOWED'", params)
    allowed = cur.fetchone()[0] or 0
    denied = total - allowed

    # Heatmap: last 7 days by weekday/hour, independent of the selected range
    hm_since = (now - timedelta(days=7)).strftime('%Y-%m-%d %H:%M:%S')
    cur.execute("""
        SELECT
            CAST(STRFTIME('%w', timestamp) AS INTEGER) AS day,
            STRFTIME('%H', timestamp) AS hour,
            COUNT(*) AS count
        FROM access_logs
        WHERE timestamp >= ?
        GROUP BY day, hour
    """, (hm_since,))
    heatmap = [{"day": r["day"], "hour": r["hour"], "count": r["count"]} for r in cur.fetchall()]

    # Timeline chart data, bucketed differently depending on the range
    line_data = _build_timeline(cur, time_range, since, since_str if since else None)

    # Busiest hour within the selected range
    cur.execute(f"""
        SELECT STRFTIME('%H', timestamp) AS hr, COUNT(*) AS cnt
        FROM access_logs {where}
        GROUP BY hr ORDER BY cnt DESC LIMIT 1
    """, params)
    ph_row = cur.fetchone()
    peak_hour = int(ph_row["hr"]) if ph_row else 0

    failure_rate = round((denied / total) * 100, 1)
    success_rate = round((allowed / total) * 100, 1)

    # Currently blocked employees
    cur.execute("""
        SELECT e.card_uid, e.full_name AS name, e.role,
               (SELECT al2.status FROM access_logs al2
                WHERE al2.card_uid = e.card_uid
                ORDER BY al2.id DESC LIMIT 1) AS reason
        FROM employees e WHERE e.is_active = 0 ORDER BY e.full_name
    """)
    blocked_employees = [dict(r) for r in cur.fetchall()]

    # Card with the most block/lock events in the selected range
    cur.execute(f"""
        SELECT al.employee_name AS name, COUNT(*) AS count
        FROM access_logs al
        WHERE al.status IN ('BLOCKED_CARD','CARD_LOCKED') {('AND timestamp >= ?' if since else '')}
        GROUP BY al.card_uid ORDER BY count DESC LIMIT 1
    """, ((since_str,) if since else ()))
    ba_row = cur.fetchone()
    blocked_analysis = {"name": ba_row["name"], "count": ba_row["count"]} if ba_row else None

    # Full employee list, for the "Manage Employees" panel
    cur.execute("""
        SELECT id, national_id, personnel_code, full_name, role, card_uid, is_active
        FROM employees ORDER BY full_name
    """)
    employees = [dict(r) for r in cur.fetchall()]

    # Count of distinct unrecognized cards in the selected range
    cur.execute(f"""
        SELECT COUNT(DISTINCT card_uid) FROM access_logs
        {where} {'AND' if where else 'WHERE'} status='UNKNOWN_CARD'
    """, params)
    unknown_count = cur.fetchone()[0] or 0

    conn.close()

    return jsonify({
        "total": total,
        "allowed": allowed,
        "denied": denied,
        "failure_rate": failure_rate,
        "success_rate": success_rate,
        "peak_hour": str(peak_hour).zfill(2),
        "heatmap": heatmap,
        "line": line_data,
        "blocked_employees": blocked_employees,
        "blocked_analysis": blocked_analysis,
        "employees": employees,
        "unknown_count": unknown_count,
    })


def _build_timeline(cur, time_range, since, since_str):
    """Build timeline chart points; bucket size depends on the selected range."""
    now = datetime.now()

    if time_range == '24h':
        # 12 points, one every 2 hours
        points = []
        for i in range(11, -1, -1):
            slot_end = now - timedelta(hours=i * 2)
            slot_start = slot_end - timedelta(hours=2)
            label = slot_end.strftime('%H:00')
            s = slot_start.strftime('%Y-%m-%d %H:%M:%S')
            e = slot_end.strftime('%Y-%m-%d %H:%M:%S')
            cur.execute("SELECT COUNT(*) FROM access_logs WHERE timestamp BETWEEN ? AND ? AND status='ALLOWED'", (s, e))
            granted = cur.fetchone()[0]
            cur.execute("SELECT COUNT(*) FROM access_logs WHERE timestamp BETWEEN ? AND ? AND status!='ALLOWED'", (s, e))
            denied_slot = cur.fetchone()[0]
            points.append({"label": label, "granted": granted, "denied": denied_slot})
        return points

    elif time_range in ('7d', None, ''):
        # 7 points, one per day
        points = []
        for i in range(6, -1, -1):
            d = (now - timedelta(days=i)).strftime('%Y-%m-%d')
            label = (now - timedelta(days=i)).strftime('%a %d')
            cur.execute("SELECT COUNT(*) FROM access_logs WHERE timestamp LIKE ? AND status='ALLOWED'", (d + '%',))
            granted = cur.fetchone()[0]
            cur.execute("SELECT COUNT(*) FROM access_logs WHERE timestamp LIKE ? AND status!='ALLOWED'", (d + '%',))
            denied_day = cur.fetchone()[0]
            points.append({"label": label, "granted": granted, "denied": denied_day})
        return points

    elif time_range == '30d':
        # 4 points, one per week
        points = []
        for i in range(3, -1, -1):
            week_end = now - timedelta(weeks=i)
            week_start = week_end - timedelta(weeks=1)
            label = week_start.strftime('%b %d')
            s = week_start.strftime('%Y-%m-%d')
            e = week_end.strftime('%Y-%m-%d')
            cur.execute("SELECT COUNT(*) FROM access_logs WHERE DATE(timestamp) BETWEEN ? AND ? AND status='ALLOWED'", (s, e))
            granted = cur.fetchone()[0]
            cur.execute("SELECT COUNT(*) FROM access_logs WHERE DATE(timestamp) BETWEEN ? AND ? AND status!='ALLOWED'", (s, e))
            denied_w = cur.fetchone()[0]
            points.append({"label": label, "granted": granted, "denied": denied_w})
        return points

    else:
        # 90d / all-time: monthly buckets
        points = []
        months = 3 if time_range == '90d' else 6
        for i in range(months - 1, -1, -1):
            d = now - timedelta(days=i * 30)
            month_str = d.strftime('%Y-%m')
            label = d.strftime('%b %Y')
            cur.execute("SELECT COUNT(*) FROM access_logs WHERE strftime('%Y-%m',timestamp)=? AND status='ALLOWED'", (month_str,))
            granted = cur.fetchone()[0]
            cur.execute("SELECT COUNT(*) FROM access_logs WHERE strftime('%Y-%m',timestamp)=? AND status!='ALLOWED'", (month_str,))
            denied_m = cur.fetchone()[0]
            points.append({"label": label, "granted": granted, "denied": denied_m})
        return points


# POST /scan — called by the physical card reader
@app.route('/scan', methods=['POST'])
def scan_card():
    data = request.json or {}
    card_uid = data.get('uid', '').strip().upper()
    submitted_pin = data.get('pin', '').strip()

    print(f"--- [SCAN] Card: {card_uid} | PIN: {submitted_pin} ---")

    if not card_uid:
        return 'U'

    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    gate = "Biotech Lab Main Gate"

    cur.execute("SELECT full_name, pin_code, is_active, failed_attempts FROM employees WHERE card_uid=?", (card_uid,))
    user = cur.fetchone()

    # Unknown card: log and reject
    if not user:
        cur.execute("INSERT INTO access_logs VALUES (NULL,?,?,?,?,?)",
                    (card_uid, "Unknown Stranger", current_time, gate, "UNKNOWN_CARD"))
        conn.commit(), conn.close()
        return 'U'

    name, correct_pin, is_active, failed_attempts = user

    # Card is blocked
    if is_active == 0:
        cur.execute("INSERT INTO access_logs VALUES (NULL,?,?,?,?,?)",
                    (card_uid, name, current_time, gate, "BLOCKED_CARD"))
        conn.commit(), conn.close()
        return 'L'

    # Card is valid but PIN hasn't been entered yet
    if not submitted_pin:
        conn.close()
        return 'P'

    if submitted_pin == correct_pin:
        # Correct PIN: reset failed attempts and grant access
        cur.execute("UPDATE employees SET failed_attempts=0 WHERE card_uid=?", (card_uid,))
        cur.execute("INSERT INTO access_logs VALUES (NULL,?,?,?,?,?)",
                    (card_uid, name, current_time, gate, "ALLOWED"))
        conn.commit(), conn.close()
        return 'A'
    else:
        # Wrong PIN: count the attempt, lock the card after 3 failures
        new_attempts = failed_attempts + 1
        if new_attempts >= 3:
            cur.execute("UPDATE employees SET is_active=0, failed_attempts=? WHERE card_uid=?", (new_attempts, card_uid))
            cur.execute("INSERT INTO access_logs VALUES (NULL,?,?,?,?,?)",
                        (card_uid, name, current_time, gate, "CARD_LOCKED"))
            conn.commit(), conn.close()
            return 'L'
        else:
            cur.execute("UPDATE employees SET failed_attempts=? WHERE card_uid=?", (new_attempts, card_uid))
            cur.execute("INSERT INTO access_logs VALUES (NULL,?,?,?,?,?)",
                        (card_uid, name, current_time, gate, "DENIED_PIN"))
            conn.commit(), conn.close()
            return 'W'


# POST /unblock/<card_uid> — reactivate a blocked badge
@app.route('/unblock/<card_uid>', methods=['POST'])
def unblock(card_uid):
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    cur.execute("UPDATE employees SET is_active=1, failed_attempts=0 WHERE card_uid=?", (card_uid,))
    if cur.rowcount == 0:
        conn.close()
        return jsonify({"success": False, "error": "Card not found"})
    conn.commit(), conn.close()
    return jsonify({"success": True})


# POST /block/<card_uid> — manually block a badge
@app.route('/block/<card_uid>', methods=['POST'])
def block(card_uid):
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    cur.execute("UPDATE employees SET is_active=0 WHERE card_uid=?", (card_uid,))
    if cur.rowcount == 0:
        conn.close()
        return jsonify({"success": False, "error": "Card not found"})

    # Log the manual block
    cur.execute("SELECT full_name FROM employees WHERE card_uid=?", (card_uid,))
    row = cur.fetchone()
    name = row[0] if row else "Unknown"
    cur.execute("INSERT INTO access_logs VALUES (NULL,?,?,?,?,?)",
                (card_uid, name, datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                 "Biotech Lab Main Gate", "BLOCKED_CARD"))
    conn.commit(), conn.close()
    return jsonify({"success": True})


# POST /add_employee
@app.route('/add_employee', methods=['POST'])
def add_employee():
    full_name    = request.form.get('full_name', '').strip()
    role         = request.form.get('role', '').strip()
    national_id  = request.form.get('national_id', '').strip()
    personnel_code = request.form.get('personnel_code', '').strip()
    card_uid     = request.form.get('card_uid', '').strip()
    pin_code     = request.form.get('pin_code', '').strip()

    if not all([full_name, national_id, card_uid, pin_code]):
        return jsonify({"success": False, "error": "Required fields missing"})

    try:
        conn = sqlite3.connect(DB_NAME)
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO employees (national_id, personnel_code, full_name, role, card_uid, pin_code, is_active)
            VALUES (?,?,?,?,?,?,1)
        """, (national_id, personnel_code, full_name, role, card_uid, pin_code))
        conn.commit(), conn.close()
        return jsonify({"success": True})
    except sqlite3.IntegrityError:
        return jsonify({"success": False, "error": "Duplicate national ID or card UID"})


# POST /edit_employee/<id>
@app.route('/edit_employee/<int:emp_id>', methods=['POST'])
def edit_employee(emp_id):
    full_name      = request.form.get('full_name', '').strip()
    role           = request.form.get('role', '').strip()
    national_id    = request.form.get('national_id', '').strip()
    personnel_code = request.form.get('personnel_code', '').strip()
    card_uid       = request.form.get('card_uid', '').strip()
    pin_code       = request.form.get('pin_code', '').strip()

    if not all([full_name, national_id, card_uid]):
        return jsonify({"success": False, "error": "Required fields missing"})

    try:
        conn = sqlite3.connect(DB_NAME)
        cur = conn.cursor()
        if pin_code:
            # PIN provided: update it along with the rest of the fields
            cur.execute("""
                UPDATE employees SET full_name=?, role=?, national_id=?, personnel_code=?,
                card_uid=?, pin_code=? WHERE id=?
            """, (full_name, role, national_id, personnel_code, card_uid, pin_code, emp_id))
        else:
            # PIN left blank: keep the existing PIN unchanged
            cur.execute("""
                UPDATE employees SET full_name=?, role=?, national_id=?, personnel_code=?,
                card_uid=? WHERE id=?
            """, (full_name, role, national_id, personnel_code, card_uid, emp_id))
        conn.commit(), conn.close()
        return jsonify({"success": True})
    except sqlite3.IntegrityError:
        return jsonify({"success": False, "error": "Duplicate national ID or card UID"})


# POST /emergency_open — manual override to log an emergency exit
@app.route('/emergency_open', methods=['POST'])
def emergency_open():
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    cur.execute("INSERT INTO access_logs VALUES (NULL,?,?,?,?,?)",
                ("SYSTEM", "Emergency Override",
                 datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                 "Biotech Lab Main Gate", "EMERGENCY_EXIT"))
    conn.commit(), conn.close()
    return jsonify({"success": True, "message": "Emergency exit triggered"})


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)