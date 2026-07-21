from flask import Flask, render_template, request, jsonify, session, redirect, url_for, send_file
import os
import uuid
import time
import csv
import io
import sqlite3
from datetime import datetime

from database import get_db, init_db
from auth_logic import login_required, generate_code, send_login_code_email
from qr_logic import get_client_ip, is_school_wifi, make_qr_image

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "camtech-attendance-2025-secret")

SCHOOL_WIFI_SUBNET = os.environ.get("SCHOOL_WIFI_SUBNET", "192.168.")
BYPASS_WIFI_CHECK = os.environ.get("BYPASS_WIFI_CHECK", "false").lower() == "true"
QR_EXPIRE_SECONDS = 10
LOGIN_CODE_EXPIRE_SECONDS = 300  # login code stays valid for 5 minutes; resend is manual

# In-memory storage for active QR sessions
active_qr_sessions = {}

# In-memory storage for pending email login codes, keyed by email.
# {"code": "123456", "expires_at": ts}
active_login_codes = {}


# ───────────────────────────── Auth: email + code ───────────────────────────

@app.route("/")
def index():
    if "teacher_id" in session:
        return redirect(url_for("dashboard"))
    return redirect(url_for("login"))


def _issue_login_code(email):
    code = generate_code()
    active_login_codes[email] = {
        "code": code,
        "expires_at": time.time() + LOGIN_CODE_EXPIRE_SECONDS,
    }
    sent_real_email = send_login_code_email(email, code)
    session["pending_email"] = email
    # If no SMTP is configured, show the code right on the page so testing
    # doesn't require watching the server terminal.
    session["dev_code"] = None if sent_real_email else code


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        conn = get_db()
        teacher = conn.execute(
            "SELECT * FROM teachers WHERE lower(email)=?", (email,)
        ).fetchone()
        conn.close()

        if not teacher:
            # No account yet for this email — offer to register instead of
            # just failing, so professors don't need manual DB access.
            return render_template("login.html",
                                    error="No professor account found for that email.",
                                    unknown_email=email)

        _issue_login_code(email)
        return redirect(url_for("login_verify"))

    return render_template("login.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        name = request.form.get("name", "").strip()

        if not email or not name:
            return render_template("register.html", error="Email and full name are required.",
                                    email=email, name=name)

        conn = get_db()
        existing = conn.execute(
            "SELECT * FROM teachers WHERE lower(email)=?", (email,)
        ).fetchone()
        if existing:
            conn.close()
            return render_template("register.html",
                                    error="An account already exists for that email — log in instead.",
                                    email=email, name=name)

        conn.execute("INSERT INTO teachers (email, name) VALUES (?, ?)", (email, name))
        conn.commit()
        conn.close()

        _issue_login_code(email)
        return redirect(url_for("login_verify"))

    prefill_email = request.args.get("email", "")
    return render_template("register.html", email=prefill_email)


@app.route("/login/verify", methods=["GET", "POST"])
def login_verify():
    email = session.get("pending_email")
    if not email:
        return redirect(url_for("login"))
    dev_code = session.get("dev_code")

    if request.method == "POST":
        entered = request.form.get("code", "").strip()
        entry = active_login_codes.get(email)

        if not entry or time.time() >= entry["expires_at"]:
            return render_template("login_verify.html", email=email, dev_code=dev_code,
                                    error="Your code expired. Click 'Resend Code' to get a new one.")

        if entered and entered == entry["code"]:
            conn = get_db()
            teacher = conn.execute(
                "SELECT * FROM teachers WHERE lower(email)=?", (email,)
            ).fetchone()
            conn.close()
            active_login_codes.pop(email, None)
            session.pop("pending_email", None)
            session.pop("dev_code", None)
            session["teacher_id"] = teacher["id"]
            session["teacher_name"] = teacher["name"]
            session["teacher_email"] = teacher["email"]
            return redirect(url_for("dashboard"))

        return render_template("login_verify.html", email=email, dev_code=dev_code,
                                error="Incorrect code. Please check your email and try again.")

    return render_template("login_verify.html", email=email, dev_code=dev_code)


@app.route("/api/login-code/resend", methods=["POST"])
def resend_login_code():
    """Manually issues a brand new code and re-sends it (button click only —
    the code does not auto-rotate on its own)."""
    email = session.get("pending_email")
    if not email:
        return jsonify({"error": "No pending login."}), 400

    new_code = generate_code()
    active_login_codes[email] = {
        "code": new_code,
        "expires_at": time.time() + LOGIN_CODE_EXPIRE_SECONDS,
    }
    sent_real_email = send_login_code_email(email, new_code)
    session["dev_code"] = None if sent_real_email else new_code

    return jsonify({
        "ok": True,
        "sent_real_email": sent_real_email,
        "dev_code": session["dev_code"],
    })


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


# ───────────────────────────── Dashboard / Subjects ─────────────────────────

@app.route("/dashboard")
@login_required
def dashboard():
    conn = get_db()
    subjects = conn.execute("""
        SELECT sub.id, sub.name,
               COUNT(DISTINCT st.student_id) AS student_count,
               COUNT(DISTINCT sess.id) AS session_count,
               SUM(CASE WHEN sess.ended_at IS NULL THEN 1 ELSE 0 END) AS active_count
        FROM subjects sub
        LEFT JOIN students st ON st.subject_id = sub.id
        LEFT JOIN attendance_sessions sess ON sess.subject_id = sub.id
        GROUP BY sub.id
        ORDER BY sub.name ASC
    """).fetchall()
    conn.close()
    return render_template("dashboard.html",
                           teacher_name=session["teacher_name"],
                           subjects=subjects)


@app.route("/api/subjects/add", methods=["POST"])
@login_required
def add_subject():
    d = request.get_json() or {}
    name = (d.get("name") or "").strip()
    if not name:
        return jsonify({"ok": False, "error": "Subject name is required."}), 400
    try:
        conn = get_db()
        cur = conn.execute(
            "INSERT INTO subjects (name, created_by) VALUES (?, ?)",
            (name, session["teacher_id"])
        )
        conn.commit()
        new_id = cur.lastrowid
        conn.close()
        return jsonify({"ok": True, "id": new_id, "name": name})
    except sqlite3.IntegrityError:
        return jsonify({"ok": False, "error": "A subject with that name already exists."}), 400


@app.route("/subject/<int:subject_id>")
@login_required
def subject_page(subject_id):
    conn = get_db()
    subject = conn.execute("SELECT * FROM subjects WHERE id=?", (subject_id,)).fetchone()
    if not subject:
        conn.close()
        return "Subject not found", 404

    sessions = conn.execute("""
        SELECT s.id, s.started_at, s.ended_at, t.name AS teacher_name,
               COUNT(r.id) AS student_count
        FROM attendance_sessions s
        LEFT JOIN attendance_records r ON r.session_id = s.id
        LEFT JOIN teachers t ON t.id = s.teacher_id
        WHERE s.subject_id = ?
        GROUP BY s.id
        ORDER BY s.started_at DESC
        LIMIT 30
    """, (subject_id,)).fetchall()

    total_sessions = conn.execute(
        "SELECT COUNT(*) AS c FROM attendance_sessions WHERE subject_id=?", (subject_id,)
    ).fetchone()["c"]

    roster = conn.execute("""
        SELECT st.student_id, st.name, st.major,
               (SELECT COUNT(*) FROM attendance_records r
                JOIN attendance_sessions se ON se.id = r.session_id
                WHERE r.student_id = st.student_id AND se.subject_id = ?) AS attended_count
        FROM students st
        WHERE st.subject_id = ?
        ORDER BY st.name ASC
    """, (subject_id, subject_id)).fetchall()
    conn.close()

    return render_template("subject.html",
                           subject=subject,
                           sessions=sessions,
                           total_sessions=total_sessions,
                           roster=roster)


# ───────────────────────────── QR Sessions ──────────────────────────────────

@app.route("/session/start", methods=["POST"])
@login_required
def start_session():
    subject_id = request.form.get("subject_id", "").strip()
    if not subject_id:
        return jsonify({"error": "Subject is required"}), 400

    conn = get_db()
    subject = conn.execute("SELECT * FROM subjects WHERE id=?", (subject_id,)).fetchone()
    if not subject:
        conn.close()
        return jsonify({"error": "Subject not found"}), 404

    sess_id = str(uuid.uuid4())
    now = datetime.now().isoformat()

    conn.execute("""
        INSERT INTO attendance_sessions (id, subject_id, teacher_id, started_at)
        VALUES (?, ?, ?, ?)
    """, (sess_id, subject_id, session["teacher_id"], now))
    conn.commit()
    conn.close()

    active_qr_sessions[sess_id] = {
        "token": str(uuid.uuid4()),
        "expires_at": time.time() + QR_EXPIRE_SECONDS,
        "subject_id": subject_id,
        "subject_name": subject["name"],
    }
    return jsonify({"session_id": sess_id, "subject_id": subject_id, "subject_name": subject["name"]})


@app.route("/session/<sess_id>/end", methods=["POST"])
@login_required
def end_session(sess_id):
    conn = get_db()
    conn.execute("""
        UPDATE attendance_sessions SET ended_at=? WHERE id=? AND teacher_id=?
    """, (datetime.now().isoformat(), sess_id, session["teacher_id"]))
    conn.commit()
    conn.close()
    active_qr_sessions.pop(sess_id, None)
    return jsonify({"ok": True})


@app.route("/session/<sess_id>/qr")
@login_required
def session_qr_page(sess_id):
    conn = get_db()
    sess = conn.execute("""
        SELECT s.*, sub.name AS subject_name
        FROM attendance_sessions s
        JOIN subjects sub ON sub.id = s.subject_id
        WHERE s.id=? AND s.teacher_id=?
    """, (sess_id, session["teacher_id"])).fetchone()
    conn.close()
    if not sess:
        return "Session not found", 404
    return render_template("teacher_qr.html",
                           session_id=sess_id,
                           subject_name=sess["subject_name"])


@app.route("/api/qr/<sess_id>")
@login_required
def api_get_qr(sess_id):
    if sess_id not in active_qr_sessions:
        return jsonify({"error": "Session not active"}), 404

    qr_data = active_qr_sessions[sess_id]
    now = time.time()

    if now >= qr_data["expires_at"]:
        qr_data["token"] = str(uuid.uuid4())
        qr_data["expires_at"] = now + QR_EXPIRE_SECONDS

    remaining = max(0, int(qr_data["expires_at"] - now))
    student_url = request.host_url + f"attend/{sess_id}/{qr_data['token']}"
    qr_b64 = make_qr_image(student_url)

    return jsonify({
        "qr_image": qr_b64,
        "remaining": remaining,
        "token": qr_data["token"],
        "student_url": student_url,
    })


@app.route("/session/<sess_id>/records")
@login_required
def session_records(sess_id):
    conn = get_db()
    sess = conn.execute("""
        SELECT s.*, sub.name AS subject_name
        FROM attendance_sessions s
        JOIN subjects sub ON sub.id = s.subject_id
        WHERE s.id=?
    """, (sess_id,)).fetchone()

    records = conn.execute("""
        SELECT r.*, s.name AS student_name
        FROM attendance_records r
        JOIN students s ON r.student_id = s.student_id
        WHERE r.session_id=?
        ORDER BY r.timestamp ASC
    """, (sess_id,)).fetchall()
    conn.close()

    if not sess:
        return "Session not found", 404
    return render_template("records.html", session=sess, records=records)


@app.route("/session/<sess_id>/export")
@login_required
def export_csv(sess_id):
    conn = get_db()
    sess = conn.execute("""
        SELECT s.*, sub.name AS subject_name
        FROM attendance_sessions s
        JOIN subjects sub ON sub.id = s.subject_id
        WHERE s.id=?
    """, (sess_id,)).fetchone()

    records = conn.execute("""
        SELECT r.student_id, s.name AS student_name, r.timestamp, r.device_id
        FROM attendance_records r
        JOIN students s ON r.student_id = s.student_id
        WHERE r.session_id=?
        ORDER BY r.timestamp ASC
    """, (sess_id,)).fetchall()
    conn.close()

    if not sess:
        return "Not found", 404

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["No.", "Student ID", "Student Name", "Subject", "Timestamp", "Device ID"])
    for i, r in enumerate(records, 1):
        writer.writerow([i, r["student_id"], r["student_name"],
                         sess["subject_name"], r["timestamp"], r["device_id"] or ""])

    buf.seek(0)
    filename = f"attendance_{sess['subject_name'].replace(' ', '_')}_{sess['started_at'][:10]}.csv"
    return send_file(
        io.BytesIO(buf.getvalue().encode()),
        mimetype="text/csv",
        as_attachment=True,
        download_name=filename,
    )


@app.route("/api/session/<sess_id>/count")
@login_required
def session_count(sess_id):
    conn = get_db()
    count = conn.execute(
        "SELECT COUNT(*) as c FROM attendance_records WHERE session_id=?",
        (sess_id,)
    ).fetchone()["c"]
    conn.close()
    return jsonify({"count": count})


# ───────────────────────────── Student check-in ─────────────────────────────

@app.route("/attend/<sess_id>/<token>")
def student_attend(sess_id, token):
    ip = get_client_ip(request)

    if not is_school_wifi(ip, SCHOOL_WIFI_SUBNET, BYPASS_WIFI_CHECK):
        return render_template("student_attend.html",
                               blocked=True,
                               reason="You must be connected to the school WiFi.")

    if sess_id not in active_qr_sessions:
        return render_template("student_attend.html",
                               blocked=True,
                               reason="This session is no longer active.")

    qr_data = active_qr_sessions[sess_id]

    if time.time() >= qr_data["expires_at"]:
        return render_template("student_attend.html",
                               blocked=True,
                               reason="QR code expired. Please re-scan.")

    if qr_data["token"] != token:
        return render_template("student_attend.html",
                               blocked=True,
                               reason="Invalid QR code.")

    return render_template("student_attend.html",
                           blocked=False,
                           session_id=sess_id,
                           token=token,
                           subject_name=qr_data["subject_name"])


@app.route("/api/attend/submit", methods=["POST"])
def submit_attendance():
    data = request.get_json()
    sess_id    = data.get("session_id", "")
    token      = data.get("token", "")
    student_id = data.get("student_id", "").strip().upper()
    device_id  = data.get("device_id", "")
    ip = get_client_ip(request)

    if not is_school_wifi(ip, SCHOOL_WIFI_SUBNET, BYPASS_WIFI_CHECK):
        return jsonify({"ok": False, "error": "Not on school WiFi."}), 403

    if sess_id not in active_qr_sessions:
        return jsonify({"ok": False, "error": "Session not active."}), 400

    qr_data = active_qr_sessions[sess_id]
    if time.time() >= qr_data["expires_at"]:
        return jsonify({"ok": False, "error": "QR code expired."}), 400

    if qr_data["token"] != token:
        return jsonify({"ok": False, "error": "Invalid QR."}), 400

    if not student_id:
        return jsonify({"ok": False, "error": "Enter your Student ID."}), 400

    if not device_id:
        return jsonify({"ok": False, "error": "Could not identify this device."}), 400

    conn = get_db()
    student = conn.execute(
        "SELECT * FROM students WHERE student_id=?", (student_id,)
    ).fetchone()

    if not student:
        conn.close()
        return jsonify({"ok": False, "error": "Student ID not found."}), 400

    # One phone binds permanently to one student. If this phone was already
    # used to check in a *different* student before, block it (anti-proxy).
    device_row = conn.execute(
        "SELECT * FROM devices WHERE device_id=?", (device_id,)
    ).fetchone()

    if device_row and device_row["student_id"] != student_id:
        conn.close()
        return jsonify({
            "ok": False,
            "error": "This phone is already registered to another student and cannot be used for this ID."
        }), 403

    # Prevent duplicate attendance within the same session
    dup = conn.execute(
        "SELECT id FROM attendance_records WHERE session_id=? AND (student_id=? OR device_id=?)",
        (sess_id, student_id, device_id)
    ).fetchone()

    if dup:
        conn.close()
        return jsonify({"ok": False, "error": "Attendance already marked."}), 409

    now = datetime.now().isoformat()
    conn.execute("""
        INSERT INTO attendance_records
            (session_id, student_id, device_id, timestamp)
        VALUES (?, ?, ?, ?)
    """, (sess_id, student_id, device_id, now))

    if not device_row:
        conn.execute("""
            INSERT INTO devices (device_id, student_id, first_seen)
            VALUES (?, ?, ?)
        """, (device_id, student_id, now))

    conn.commit()
    conn.close()

    return jsonify({
        "ok": True,
        "student_name": student["name"],
        "subject_name": qr_data["subject_name"],
        "timestamp": now,
    })


# ───────────────────────────── Student management ───────────────────────────

@app.route("/students")
@login_required
def manage_students():
    conn = get_db()
    students = conn.execute("""
        SELECT st.*, sub.name AS subject_name
        FROM students st
        JOIN subjects sub ON sub.id = st.subject_id
        ORDER BY sub.name, st.name
    """).fetchall()
    subjects = conn.execute("SELECT * FROM subjects ORDER BY name ASC").fetchall()
    conn.close()
    return render_template("students.html", students=students, subjects=subjects)


@app.route("/api/students/add", methods=["POST"])
@login_required
def add_student():
    d = request.get_json()
    try:
        conn = get_db()
        conn.execute(
            "INSERT INTO students (student_id, name, major, subject_id) VALUES (?,?,?,?)",
            (d["student_id"].upper(), d["name"], d.get("major", ""), d["subject_id"])
        )
        conn.commit()
        subj = conn.execute("SELECT name FROM subjects WHERE id=?", (d["subject_id"],)).fetchone()
        conn.close()
        return jsonify({"ok": True, "subject_name": subj["name"] if subj else ""})
    except sqlite3.IntegrityError:
        return jsonify({"ok": False, "error": "Student ID already exists."}), 400


@app.route("/api/students/delete/<sid>", methods=["DELETE"])
@login_required
def delete_student(sid):
    conn = get_db()
    conn.execute("DELETE FROM students WHERE student_id=?", (sid,))
    conn.commit()
    conn.close()
    return jsonify({"ok": True})


if __name__ == "__main__":
    init_db()
    app.run(debug=True, host="0.0.0.0", port=5000)
