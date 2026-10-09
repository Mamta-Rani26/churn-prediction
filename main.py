import io, os, json, uuid, secrets
import joblib
import pandas as pd
from fastapi import FastAPI, UploadFile, File, Form, HTTPException, Request
from fastapi.responses import FileResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware
from report_engine import build_report
import auth

app = FastAPI(title="Churn Prediction")

SECRET_KEY = os.environ.get("SECRET_KEY", "dev-secret-change-me")
# Set HTTPS_ONLY=1 in .env when the site is served over HTTPS
app.add_middleware(SessionMiddleware, secret_key=SECRET_KEY, max_age=3600,
                   same_site="lax", https_only=os.environ.get("HTTPS_ONLY") == "1")

app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

auth.init_db()

model = joblib.load("churn_model.pkl")
metrics = json.load(open("metrics.json"))
metrics["model"] = "Customer Churn Risk Analysis"   # heading shown on pages
expected = json.load(open("expected_columns.json"))

os.makedirs("outputs", exist_ok=True)
auth.cleanup_old_reports()
MAX_SIZE = 5 * 1024 * 1024   # 5 MB

VERIFY_INFO = ("Enter the 6-digit code sent to your email. "
               "If you did not receive it, click 'Resend code' (also check your spam folder).")


class InputError(Exception):
    pass


# ---------- Helpers ----------
def current_user(request: Request):
    return request.session.get("user")


def get_csrf(request: Request) -> str:
    if "csrf" not in request.session:
        request.session["csrf"] = secrets.token_urlsafe(32)
    return request.session["csrf"]


def check_csrf(request: Request, token: str):
    expected_token = request.session.get("csrf", "")
    if not token or not expected_token or not secrets.compare_digest(token, expected_token):
        raise HTTPException(403, "Invalid or missing security token. "
                                 "Please go back, refresh the page and try again.")


def render(request: Request, name: str, context=None, status=200):
    ctx = dict(context or {})
    ctx["csrf_token"] = get_csrf(request)
    return templates.TemplateResponse(request=request, name=name,
                                      context=ctx, status_code=status)


def home_context(user, error=None):
    return {"error": error, "user": user,
            "metrics_auc": f"{metrics['roc_auc']*100:.1f}%"}


def save_report_excel(df, path):
    """Writes the report; text starting with '=' is stored as text, never as a formula."""
    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        df.to_excel(writer, index=False)
        ws = writer.sheets[list(writer.sheets)[0]]
        for row in ws.iter_rows():
            for cell in row:
                if isinstance(cell.value, str) and cell.value.startswith("="):
                    cell.data_type = "s"


async def run_prediction(file: UploadFile, user: str):
    if not file.filename or not file.filename.lower().endswith(".xlsx"):
        raise InputError("Please upload an .xlsx file only.")

    content = await file.read(MAX_SIZE + 1)   # never read more than the limit
    if len(content) > MAX_SIZE:
        raise InputError("The file is larger than 5 MB.")

    try:
        raw = pd.read_excel(io.BytesIO(content))
    except Exception:
        raise InputError("The Excel file could not be read. Please check the file.")

    if raw.empty:
        raise InputError("The file contains no data.")

    missing = [c for c in expected if c not in raw.columns]
    if missing:
        raise InputError(f"Missing required columns: {missing}")

    try:
        report = build_report(raw, model, expected)
    except Exception:
        raise InputError("Invalid values found (for example, text in a numeric column).")

    file_id = uuid.uuid4().hex
    save_report_excel(report, f"outputs/{file_id}.xlsx")
    auth.save_report(file_id, user)          # remember who owns this report
    auth.cleanup_old_reports()

    show_cols = [c for c in ["customerID", "churn_probability_%", "risk_level",
                             "recommended_offer", "probability_after_offer_%"]
                 if c in report.columns]
    top = (report.sort_values("churn_probability_%", ascending=False)
                 .head(10)[show_cols])

    return {
        "model_metrics": metrics,
        "summary": {
            "total_customers": int(len(report)),
            "high_risk": int((report["risk_level"] == "High").sum()),
            "medium_risk": int((report["risk_level"] == "Medium").sum()),
            "low_risk": int((report["risk_level"] == "Low").sum()),
            "avg_churn_probability": float(report["churn_probability_%"].mean().round(1)),
            "avg_after_offer": float(report["probability_after_offer_%"].mean().round(1)),
            "offers": [{"name": k, "count": int(v)} for k, v in
                       report.loc[report["recommended_offer"] != "No offer needed",
                                  "recommended_offer"].value_counts().items()],
        },
        "top_risk_customers": json.loads(top.to_json(orient="records")),
        "download_url": f"/download/{file_id}",
    }


# ---------- Register ----------
@app.get("/register")
def register_page(request: Request):
    return render(request, "register.html", {"error": None})


@app.post("/register")
async def register(request: Request, email: str = Form(...),
                   password: str = Form(...), confirm: str = Form(...),
                   csrf_token: str = Form("")):
    check_csrf(request, csrf_token)
    email = email.strip().lower()

    def fail(msg):
        return render(request, "register.html", {"error": msg}, 400)

    if not auth.domain_allowed(email):
        return fail("Only @poornima.edu.in email addresses can register.")
    err = auth.password_error(password)
    if err:
        return fail(err)
    if password != confirm:
        return fail("The two passwords do not match.")

    try:
        auth.create_or_update_unverified(email, password)
    except ValueError:
        return fail("This email is already registered. Please sign in.")

    try:
        ok, msg = auth.issue_otp(email)
    except Exception as e:
        print("Error while sending email:", e)
        return fail("Could not send the verification email. Please try again later.")
    if not ok:
        return fail(msg)

    request.session["pending_email"] = email
    return RedirectResponse("/verify", status_code=303)


# ---------- OTP verify ----------
@app.get("/verify")
def verify_page(request: Request):
    email = request.session.get("pending_email")
    if not email:
        return RedirectResponse("/login", status_code=303)
    return render(request, "verify.html",
                  {"email": email, "error": None, "info": VERIFY_INFO})


@app.post("/verify")
async def verify(request: Request, code: str = Form(...), csrf_token: str = Form("")):
    check_csrf(request, csrf_token)
    email = request.session.get("pending_email")
    if not email:
        return RedirectResponse("/login", status_code=303)

    ok, msg = auth.verify_otp(email, code)
    if not ok:
        return render(request, "verify.html",
                      {"email": email, "error": msg, "info": None}, 400)

    request.session.pop("pending_email", None)
    return RedirectResponse("/login", status_code=303)


@app.post("/resend-otp")
async def resend_otp(request: Request, csrf_token: str = Form("")):
    check_csrf(request, csrf_token)
    email = request.session.get("pending_email")
    if not email:
        return RedirectResponse("/login", status_code=303)

    try:
        ok, msg = auth.issue_otp(email)
    except Exception as e:
        print("Error while sending email:", e)
        ok, msg = False, "Could not send the verification email. Please try again later."

    if ok:
        return render(request, "verify.html",
                      {"email": email, "error": None,
                       "info": "A new verification code has been sent."})
    return render(request, "verify.html",
                  {"email": email, "error": msg, "info": None}, 400)


# ---------- Forgot / reset password ----------
@app.get("/forgot")
def forgot_page(request: Request):
    return render(request, "forgot.html", {"error": None})


@app.post("/forgot")
async def forgot(request: Request, email: str = Form(...), csrf_token: str = Form("")):
    check_csrf(request, csrf_token)
    email = email.strip().lower()

    def fail(msg):
        return render(request, "forgot.html", {"error": msg}, 400)

    if not auth.domain_allowed(email):
        return fail("Please enter your @poornima.edu.in email address.")

    # Same response whether or not the account exists (no account guessing)
    if auth.is_verified_user(email):
        try:
            ok, msg = auth.issue_otp(email, purpose="reset")
        except Exception as e:
            print("Error while sending email:", e)
            return fail("Could not send the email. Please try again later.")
        if not ok:
            return fail(msg)

    request.session["reset_email"] = email
    return RedirectResponse("/reset", status_code=303)


@app.get("/reset")
def reset_page(request: Request):
    email = request.session.get("reset_email")
    if not email:
        return RedirectResponse("/forgot", status_code=303)
    return render(request, "reset.html",
                  {"email": email, "error": None,
                   "info": "If this email is registered, a 6-digit code has been sent. "
                           "Check your spam folder too."})


@app.post("/reset")
async def reset(request: Request, code: str = Form(...),
                password: str = Form(...), confirm: str = Form(...),
                csrf_token: str = Form("")):
    check_csrf(request, csrf_token)
    email = request.session.get("reset_email")
    if not email:
        return RedirectResponse("/forgot", status_code=303)

    def fail(msg):
        return render(request, "reset.html",
                      {"email": email, "error": msg, "info": None}, 400)

    err = auth.password_error(password)
    if err:
        return fail(err)
    if password != confirm:
        return fail("The two passwords do not match.")

    ok, msg = auth.reset_password(email, code, password)
    if not ok:
        return fail(msg)

    request.session.clear()
    return RedirectResponse("/login?reset=1", status_code=303)


# ---------- Login / Logout ----------
@app.get("/login")
def login_page(request: Request):
    info = "Password changed successfully. Please sign in." \
        if request.query_params.get("reset") else None
    return render(request, "login.html", {"error": None, "info": info})


@app.post("/login")
async def login(request: Request, email: str = Form(...), password: str = Form(...),
                csrf_token: str = Form("")):
    check_csrf(request, csrf_token)
    email = email.strip().lower()
    key = f"{email}|{request.client.host if request.client else ''}"

    if auth.login_locked(key):
        return render(request, "login.html",
                      {"error": "Too many failed attempts. Please try again in 15 minutes."},
                      429)

    user = auth.check_login(email, password)
    if not user:
        auth.record_login_fail(key)
        return render(request, "login.html",
                      {"error": "Invalid email or password."}, 401)

    auth.clear_login_fails(key)
    if not user["verified"]:
        request.session.clear()
        request.session["pending_email"] = email
        return RedirectResponse("/verify", status_code=303)

    request.session.clear()
    request.session["user"] = user["email"]
    return RedirectResponse("/", status_code=303)


@app.post("/logout")
async def logout(request: Request, csrf_token: str = Form("")):
    check_csrf(request, csrf_token)
    request.session.clear()
    return RedirectResponse("/login", status_code=303)


# ---------- Protected pages ----------
@app.get("/")
def home(request: Request):
    user = current_user(request)
    if not user:
        return RedirectResponse("/login", status_code=303)
    return render(request, "index.html", home_context(user))


@app.post("/analyze")
async def analyze(request: Request, file: UploadFile = File(...),
                  csrf_token: str = Form("")):
    user = current_user(request)
    if not user:
        return RedirectResponse("/login", status_code=303)
    check_csrf(request, csrf_token)
    try:
        data = await run_prediction(file, user)
    except InputError as e:
        return render(request, "index.html", home_context(user, str(e)), 400)
    return render(request, "results.html", {"data": data, "user": user})


# ---------- JSON API (login required) ----------
@app.post("/predict")
async def predict(request: Request, file: UploadFile = File(...),
                  csrf_token: str = Form("")):
    user = current_user(request)
    if not user:
        raise HTTPException(401, "Login required")
    # token may come from the form field or the X-CSRF-Token header
    check_csrf(request, csrf_token or request.headers.get("x-csrf-token", ""))
    try:
        return await run_prediction(file, user)
    except InputError as e:
        raise HTTPException(400, str(e))


@app.get("/template")
def template(request: Request):
    if not current_user(request):
        return RedirectResponse("/login", status_code=303)
    buf = io.BytesIO()
    pd.DataFrame(columns=["customerID"] + expected).to_excel(buf, index=False)
    return Response(
        buf.getvalue(),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": 'attachment; filename="customer_template.xlsx"'})


@app.get("/download/{file_id}")
def download(file_id: str, request: Request):
    user = current_user(request)
    if not user:
        return RedirectResponse("/login", status_code=303)
    if not (len(file_id) == 32 and all(c in "0123456789abcdef" for c in file_id)):
        raise HTTPException(400, "Invalid file id")
    # Only the user who created the report may download it
    if auth.report_owner(file_id) != user:
        raise HTTPException(404, "File not found")
    path = f"outputs/{file_id}.xlsx"
    if not os.path.exists(path):
        raise HTTPException(404, "File not found")
    return FileResponse(path, filename="churn_report.xlsx")
