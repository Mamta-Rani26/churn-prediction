# Customer Churn Prediction System

Setup:

    pip install -r requirements.txt
    uvicorn main:app --reload

Open http://127.0.0.1:8000/login

Copy `.env.example` to `.env` and fill in your values:
SECRET_KEY (long random string), SMTP_USER, SMTP_PASS (Gmail app password).
Without SMTP settings the OTP is printed in the terminal.
Set HTTPS_ONLY=1 when the site is served over HTTPS.

Security features: CSRF tokens on all forms, POST-only logout, @poornima.edu.in only,
password rules (8-72 chars, letter + number), hashed OTP with expiry, attempt limit and
resend cooldown, login lockout after 5 wrong attempts (15 min), per-user report downloads
(old reports are deleted after 24 hours).
