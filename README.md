# QR Attendance System
**CamTech University – Computer Fundamentals Project**

A web-based attendance system where professors pick a subject/class, display a
live-rotating QR code, and students scan it on their phones to mark
attendance. Login is passwordless: each professor uses their own email and a
6-digit verification code that refreshes every 10 seconds.

---

## Features

| Feature | Detail |
|---|---|
| Email + Code Login | No passwords — each professor logs in with their own email; a 6-digit code is emailed and stays valid for a few minutes (manual "Resend Code" available anytime) |
| Self-Registration | An unrecognized email can register itself as a new professor right from the login screen |
| Subjects / Classes | Data Science & AI, Cyber Security, etc. — add more anytime from the dashboard |
| Per-Subject Sessions | Click a subject → **Start QR Attendance Session** |
| Live QR Code | Rotates every **10 seconds** automatically |
| WiFi Guard | Blocks students not on school WiFi |
| One-Phone-Per-Student | A phone is bound permanently to the first student it checks in for — it can never be used to check in a different student (anti-proxy) |
| Duplicate Prevention | Blocks the same Student ID **or** the same device twice in one session |
| Full History | Every subject keeps a permanent history of every session and every student's attendance count |
| CSV Export | Download the full attendance sheet per session |

---

## Project Structure

```
attendance-system/
├── app.py                    # Main Flask server (all routes)
├── database.py                # Schema + seed data (teachers, subjects, students, devices)
├── auth_logic.py               # Email-code generation/sending, login_required decorator
├── qr_logic.py                 # QR image generation, WiFi checks
├── requirements.txt
├── README.md
├── static/
│   ├── css/style.css          # All styles
│   └── js/dashboard.js         # Dashboard + "Add Subject" modal logic
├── templates/
│   ├── login.html              # Step 1: enter email
│   ├── login_verify.html       # Step 2: enter 6-digit code (auto-refreshes every 10s)
│   ├── dashboard.html          # Subject cards grid + "+ Add More"
│   ├── subject.html            # Subject detail: Start QR session + full history
│   ├── teacher_qr.html         # Live QR display for classroom
│   ├── student_attend.html     # Student attendance form (mobile)
│   ├── records.html            # Attendance records table for one session
│   └── students.html           # Student CRUD, assigned to a subject
└── database/
    └── attendance.db           # Auto-created on first run (SQLite)
```

---

## Quick Start

### 1. Install dependencies
```bash
pip install -r requirements.txt
```

### 2. Configure email sending (optional but recommended)
The app emails each professor a login code. Set these environment variables
to send real emails via SMTP:

```bash
export SMTP_HOST=smtp.gmail.com
export SMTP_PORT=465
export SMTP_USER=you@gmail.com
export SMTP_PASSWORD=your-app-password     # use an app password, not your real password
export SMTP_FROM=you@gmail.com
```

**If you don't configure SMTP**, the app runs in dev mode: the code is
printed to the server console/log instead of emailed, so you can still test
everything locally without a mail server.

### 3. Configure school WiFi subnet (important for real classroom use)
```bash
export SCHOOL_WIFI_SUBNET=10.0.1.       # your school's WiFi IP prefix
```
To disable the WiFi check while testing:
```bash
export BYPASS_WIFI_CHECK=true
```

### 4. Run the server
```bash
python app.py
```
Open your browser at **http://localhost:5000**

---

## Login Accounts (seeded)

Each professor has their own email — there are no shared usernames/passwords.

| Email | Name |
|---|---|
| professor1@camtech.edu.kh | Professor Dara |
| professor2@camtech.edu.kh | Professor Sophea |

Add more professors directly in the `teachers` table (or extend the app with
a "request access" flow) — edit the seed list in `database.py` → `init_db()`.

### How login works
1. Professor enters their email at `/login`. If it's not registered yet, a
   "Register this email as a new professor →" link appears.
2. A 6-digit code is generated and emailed. **If no SMTP server is
   configured**, the code is shown directly on the verify page in a clearly
   labeled "DEV MODE" box (and also printed to the server console) so you
   can test without setting up email.
3. The code stays valid for 5 minutes. If it expires or doesn't arrive, tap
   **Resend Code** to get a fresh one — it does not rotate on its own.
4. Entering the valid code logs the professor in.

---

## How to Use

### Professor
1. Log in with your email + the code from your inbox.
2. On the dashboard, click a subject (e.g. **Data Science & AI**), or
   **+ Add More** to create a new subject/class.
3. On the subject page, click **▶ Start QR Attendance Session** — a new tab
   opens with the live QR code, ready to project on the classroom screen.
4. The QR auto-refreshes every 10 seconds; the live student count updates
   every 5 seconds.
5. Click **End Session**, then use **Records** or **CSV** to review or export
   that session, or scroll the subject page to see the full attendance
   history for every student ever enrolled in that subject.

### Student
1. Connect to school WiFi.
2. Scan the QR code with their phone camera.
3. Enter their Student ID and tap **Submit Attendance**.
4. Confirmation screen shows name, subject, and timestamp.
5. Note: a phone can only ever be used to check in **one** student. If a
   phone that already checked in Student A tries to submit for Student B, it
   is blocked.

---

## Database Schema

| Table | Purpose |
|---|---|
| `teachers` | One row per professor: `id`, `email` (unique), `name` |
| `subjects` | Shared list of subjects/classes; any professor can add more |
| `students` | Enrolled students, each tied to exactly one subject |
| `attendance_sessions` | One row per QR session, scoped to a subject + professor |
| `attendance_records` | Full permanent history of every check-in, per session |
| `devices` | Phone → student binding ("one phone per student, ever") |

---

## Environment Variables

| Variable | Default | Description |
|---|---|---|
| `SECRET_KEY` | (hardcoded) | Flask session secret — change in production |
| `SCHOOL_WIFI_SUBNET` | `192.168.` | IP prefix of school WiFi |
| `BYPASS_WIFI_CHECK` | `false` | Set `true` to skip WiFi check (testing only) |
| `SMTP_HOST` | *(empty)* | SMTP server host — leave unset to use dev-mode console codes |
| `SMTP_PORT` | `465` | SMTP port (SSL) |
| `SMTP_USER` | *(empty)* | SMTP account username |
| `SMTP_PASSWORD` | *(empty)* | SMTP account password / app password |
| `SMTP_FROM` | value of `SMTP_USER` | "From" address on the login-code email |

---

## Deploying on a Local Network (for classroom use)

Flask already binds to `0.0.0.0:5000`, so just run:
```bash
python app.py
```
Find your computer's IP address (`ipconfig` on Windows, `ifconfig` on
Mac/Linux) and share `http://YOUR_IP:5000` with students, or display the QR
code directly on the classroom screen.

---

## Tech Stack

- **Backend**: Python 3.10+ / Flask
- **Database**: SQLite (via Python's built-in `sqlite3`)
- **Email**: `smtplib` (SSL) — any standard SMTP provider
- **QR Generation**: `qrcode[pil]` + Pillow
- **Frontend**: Vanilla HTML/CSS/JS (no framework)

---

## License
MIT — free to use and modify for academic purposes.
