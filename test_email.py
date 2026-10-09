"""Run this from the project folder:  python test_email.py
It checks every step of the OTP email setup and tells you what is wrong."""
import os, smtplib, sys

print("Folder:", os.getcwd())
print(".env exists here:", os.path.exists(".env"))

try:
    from dotenv import load_dotenv
    print("python-dotenv installed: YES, loaded:", load_dotenv(".env"))
except ImportError:
    print("python-dotenv installed: NO  -> run: pip install python-dotenv")
    sys.exit()

user, pw = os.environ.get("SMTP_USER"), os.environ.get("SMTP_PASS")
print("SMTP_USER:", user)
print("SMTP_PASS length:", len(pw) if pw else None, "(should be 16)")
if not user or not pw or "yourname" in user or "your16" in pw:
    print("-> Fill your real Gmail and App password in .env, then save."); sys.exit()

try:
    with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=15) as s:
        s.login(user, pw)
        print("LOGIN OK. Gmail accepted your credentials.")
        s.sendmail(user, user, f"Subject: Test\n\nIt works.")
        print("Test email sent to", user, "- check inbox/spam.")
except smtplib.SMTPAuthenticationError:
    print("LOGIN FAILED: wrong App password, or 2-Step Verification is off. Create a new App password.")
except Exception as e:
    print("CONNECTION ERROR:", repr(e), "-> check internet / firewall / college Wi-Fi blocking port 465.")
