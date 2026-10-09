import os
import time
import secrets
import hashlib
import hmac
import smtplib
import sqlite3
from email.message import EmailMessage

import bcrypt

from pathlib import Path


def _load_env():
    """Reads the .env file next to this script (no extra library needed)."""
    path = Path(__file__).resolve().parent / ".env"
    if not path.exists():
        print("[ENV] .env file not found at", path)
        return
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ[k.strip()] = v.strip().strip('"').strip("'")


_load_env()

DB = "users.db"

# Only emails from this domain can register
ALLOWED_DOMAINS = ["poornima.edu.in"]  # remove gmail.com after testing

OTP_VALID_SECONDS = 600      # OTP valid for 10 minutes
OTP_MAX_ATTEMPTS = 5         # A new OTP is required after 5 wrong attempts
RESEND_COOLDOWN = 60         # Minimum wait before requesting a new OTP

OTP_SECRET = os.environ.get("SECRET_KEY", "dev-secret-change-me")
if OTP_SECRET == "dev-secret-change-me":
    print("[WARNING] SECRET_KEY is not set. Set a long random value in .env before deploying.")


def get_db():
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with get_db() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                verified INTEGER NOT NULL DEFAULT 0,
                otp_hash TEXT,
                otp_expires INTEGER,
                otp_attempts INTEGER NOT NULL DEFAULT 0,
                otp_sent_at INTEGER NOT NULL DEFAULT 0,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)
        # Which user owns which downloadable report
        conn.execute("""
            CREATE TABLE IF NOT EXISTS reports (
                file_id TEXT PRIMARY KEY,
                email TEXT NOT NULL,
                created_at INTEGER NOT NULL
            )
        """)


def password_error(pw):
    """Returns an error message if the password breaks the rules, else None."""
    if len(pw) < 8 or len(pw.encode()) > 72:
        return "Password must be between 8 and 72 characters."
    if not any(c.isalpha() for c in pw):
        return "Password must contain at least one letter."
    if not any(c.isdigit() for c in pw):
        return "Password must contain at least one number."
    return None


# ---------- Login brute-force protection (in memory) ----------
LOGIN_MAX_FAILS = 5
LOGIN_WINDOW = 900            # 15 minutes
_FAILS = {}


def login_locked(key):
    now = time.time()
    _FAILS[key] = [t for t in _FAILS.get(key, []) if now - t < LOGIN_WINDOW]
    return len(_FAILS[key]) >= LOGIN_MAX_FAILS


def record_login_fail(key):
    _FAILS.setdefault(key, []).append(time.time())


def clear_login_fails(key):
    _FAILS.pop(key, None)


# ---------- Report ownership ----------
def save_report(file_id, email):
    with get_db() as conn:
        conn.execute("INSERT INTO reports (file_id, email, created_at) VALUES (?, ?, ?)",
                     (file_id, email, int(time.time())))


def report_owner(file_id):
    with get_db() as conn:
        row = conn.execute("SELECT email FROM reports WHERE file_id = ?",
                           (file_id,)).fetchone()
    return row["email"] if row else None


def cleanup_old_reports(max_age=86400, folder="outputs"):
    """Deletes reports older than max_age seconds (default 24 hours)."""
    cutoff = int(time.time()) - max_age
    with get_db() as conn:
        old = [r["file_id"] for r in conn.execute(
            "SELECT file_id FROM reports WHERE created_at < ?", (cutoff,))]
        conn.execute("DELETE FROM reports WHERE created_at < ?", (cutoff,))
    for fid in old:
        try:
            os.remove(os.path.join(folder, f"{fid}.xlsx"))
        except OSError:
            pass


def domain_allowed(email):
    email = email.strip().lower()
    if email.count("@") != 1:
        return False
    local, domain = email.split("@")
    return bool(local) and domain in ALLOWED_DOMAINS


def _hash_otp(email, otp):
    return hmac.new(OTP_SECRET.encode(), f"{email}:{otp}".encode(),
                    hashlib.sha256).hexdigest()


def create_or_update_unverified(email, password):
    """Creates a new unverified user. Raises ValueError if already verified."""
    pw_hash = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
    with get_db() as conn:
        row = conn.execute("SELECT verified FROM users WHERE email = ?",
                           (email,)).fetchone()
        if row and row["verified"]:
            raise ValueError("already registered")
        if row:
            conn.execute("UPDATE users SET password_hash = ? WHERE email = ?",
                         (pw_hash, email))
        else:
            conn.execute("INSERT INTO users (email, password_hash) VALUES (?, ?)",
                         (email, pw_hash))


def send_otp_email(to_email, otp, purpose="verify"):
    smtp_user = os.environ.get("SMTP_USER")
    smtp_pass = os.environ.get("SMTP_PASS")
    print(f"[MAIL] user={smtp_user}, pass_set={bool(smtp_pass)}, to={to_email}")

    # If SMTP is not configured, the OTP is printed to the terminal (testing only)
    if not smtp_user or not smtp_pass:
        print(f"[DEV MODE] OTP for {to_email}: {otp}")
        return

    msg = EmailMessage()
    if purpose == "reset":
        msg["Subject"] = "Churn Predictor - password reset code"
        intro = "Use this code to reset your password"
    else:
        msg["Subject"] = "Churn Predictor - verification code"
        intro = "Your verification code"
    msg["From"] = smtp_user
    msg["To"] = to_email
    msg.set_content(
        f"{intro}: {otp}\n\n"
        "This code is valid for 10 minutes. "
        "If you did not request this, please ignore this email."
    )
    with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=15) as server:
        server.login(smtp_user, smtp_pass)
        server.send_message(msg)


def issue_otp(email, purpose="verify"):
    """Generates a new OTP and emails it. Returns (ok, message)."""
    now = int(time.time())
    with get_db() as conn:
        row = conn.execute("SELECT otp_sent_at FROM users WHERE email = ?",
                           (email,)).fetchone()
        if not row:
            return False, "Account not found"
        wait = RESEND_COOLDOWN - (now - row["otp_sent_at"])
        if wait > 0:
            return False, f"Please wait {wait} seconds before requesting a new code"
        otp = f"{secrets.randbelow(1_000_000):06d}"
        conn.execute(
            "UPDATE users SET otp_hash = ?, otp_expires = ?, otp_attempts = 0, "
            "otp_sent_at = ? WHERE email = ?",
            (_hash_otp(email, otp), now + OTP_VALID_SECONDS, now, email))
    send_otp_email(email, otp, purpose)
    return True, None


def verify_otp(email, code):
    """Verifies the OTP. Returns (ok, message)."""
    now = int(time.time())
    code = code.strip()
    with get_db() as conn:
        row = conn.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
        if not row:
            return False, "Account not found"
        if row["verified"]:
            return True, None
        if not row["otp_hash"] or now > (row["otp_expires"] or 0):
            return False, "The code has expired. Please request a new one."
        if row["otp_attempts"] >= OTP_MAX_ATTEMPTS:
            return False, "Too many wrong attempts. Please request a new code."
        if not hmac.compare_digest(row["otp_hash"], _hash_otp(email, code)):
            conn.execute(
                "UPDATE users SET otp_attempts = otp_attempts + 1 WHERE email = ?",
                (email,))
            return False, "Incorrect verification code"
        conn.execute(
            "UPDATE users SET verified = 1, otp_hash = NULL, otp_expires = NULL, "
            "otp_attempts = 0 WHERE email = ?", (email,))
    return True, None


_DUMMY_HASH = bcrypt.hashpw(b"dummy-password", bcrypt.gensalt())


def check_login(email, password):
    with get_db() as conn:
        row = conn.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
    if not row:
        bcrypt.checkpw(password.encode(), _DUMMY_HASH)   # same timing as a real check
        return None
    if bcrypt.checkpw(password.encode(), row["password_hash"].encode()):
        return row
    return None


def is_verified_user(email):
    with get_db() as conn:
        row = conn.execute("SELECT verified FROM users WHERE email = ?",
                           (email,)).fetchone()
    return bool(row and row["verified"])


def reset_password(email, code, new_password):
    """Checks the emailed code and sets a new password. Returns (ok, message)."""
    now = int(time.time())
    code = code.strip()
    generic = "The code is invalid or has expired. Please request a new one."
    with get_db() as conn:
        row = conn.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
        if not row or not row["verified"] or not row["otp_hash"] \
                or now > (row["otp_expires"] or 0):
            return False, generic
        if row["otp_attempts"] >= OTP_MAX_ATTEMPTS:
            return False, "Too many wrong attempts. Please request a new code."
        if not hmac.compare_digest(row["otp_hash"], _hash_otp(email, code)):
            conn.execute(
                "UPDATE users SET otp_attempts = otp_attempts + 1 WHERE email = ?",
                (email,))
            return False, "Incorrect code"
        pw_hash = bcrypt.hashpw(new_password.encode(), bcrypt.gensalt()).decode()
        conn.execute(
            "UPDATE users SET password_hash = ?, otp_hash = NULL, otp_expires = NULL, "
            "otp_attempts = 0 WHERE email = ?", (pw_hash, email))
    return True, None
