import os
import random
import smtplib
import ssl
from email.mime.text import MIMEText
from functools import wraps
from flask import session, redirect, url_for

# ── Email delivery config (set these env vars for real email sending) ───────
SMTP_HOST     = os.environ.get("SMTP_HOST", "")
SMTP_PORT     = int(os.environ.get("SMTP_PORT", "465"))
SMTP_USER     = os.environ.get("SMTP_USER", "")
SMTP_PASSWORD = os.environ.get("SMTP_PASSWORD", "")
SMTP_FROM     = os.environ.get("SMTP_FROM", SMTP_USER or "no-reply@attendance.local")

CODE_LENGTH = 6


def generate_code() -> str:
    return "".join(random.choices("0123456789", k=CODE_LENGTH))


def send_login_code_email(to_email: str, code: str) -> bool:
    """
    Sends the one-time login code to the professor's email.
    If SMTP_HOST is not configured, falls back to printing the code to the
    server console so the app is still testable without a mail server.
    Returns True if an email was actually sent, False if it just logged.
    """
    subject = "Your QR Attendance login code"
    body = (
        f"Your verification code is: {code}\n\n"
        f"This code refreshes every 10 seconds, so use the most recent one "
        f"you received. It expires quickly — if it stops working, wait for "
        f"the next email.\n"
    )

    if not SMTP_HOST:
        print(f"[DEV MODE] Login code for {to_email}: {code}  "
              f"(configure SMTP_HOST/SMTP_USER/SMTP_PASSWORD to send real emails)")
        return False

    msg = MIMEText(body)
    msg["Subject"] = subject
    msg["From"] = SMTP_FROM
    msg["To"] = to_email

    try:
        context = ssl.create_default_context()
        with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT, context=context) as server:
            server.login(SMTP_USER, SMTP_PASSWORD)
            server.sendmail(SMTP_FROM, [to_email], msg.as_string())
        return True
    except Exception as e:
        print(f"[EMAIL ERROR] Could not send to {to_email}: {e}")
        print(f"[DEV MODE FALLBACK] Login code for {to_email}: {code}")
        return False


def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if "teacher_id" not in session:
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return decorated
