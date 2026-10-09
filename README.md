# Customer Churn Prediction System

A machine learning web application that predicts which customers are likely to leave and recommends the retention offer that reduces their risk the most. Built as a Final Year Project.

HR or business teams upload an Excel file of customers, and the system returns a churn probability, a risk level and the best retention offer for every customer, along with a downloadable report.

## Features

- **Churn prediction**: churn probability (%) for every customer in the uploaded file
- **Risk levels**: High (60% and above), Medium (30% to 60%), Low (below 30%)
- **Retention offer engine**: tests several offers for each customer and recommends the one that lowers the churn probability the most
- **Before and after view**: shows the average risk before and after applying the offers
- **Results dashboard**: risk distribution chart, offer summary and the top 10 customers at risk
- **Excel report**: full report with all predictions, available for download
- **Excel template**: ready-made template with the required columns
- **Secure login system**: registration with email OTP verification, login, forgot and reset password

## Retention offers

| Offer | Who is eligible |
|-------|-----------------|
| 1-year contract + 10% discount | Month-to-month customers |
| 2-year contract + 15% discount | Customers not on a 2-year contract |
| Free tech support (6 months) | Internet customers without tech support |
| Free online security (6 months) | Internet customers without online security |
| Autopay incentive | Customers paying by electronic or mailed check |
| 15% bill discount | All customers with monthly charges |

For each customer the model re-scores the churn probability with every eligible offer applied and picks the offer with the lowest result. Low-risk customers get "No offer needed".

## Model performance

The model is a Logistic Regression classifier. These scores are measured on a held-out test set, not on the file you upload.

| Metric | Score |
|--------|-------|
| Accuracy | 73.7% |
| Precision | 50.3% |
| Recall | 78.3% |
| F1-score | 61.2% |
| ROC-AUC | 84.2% |

The model is tuned for high recall, so it catches most customers who would actually leave, at the cost of some false alarms.

## Tech stack

| Part | Technology |
|------|------------|
| Backend | Python, FastAPI |
| Machine learning | scikit-learn, pandas, NumPy |
| Frontend | HTML, CSS, JavaScript (Jinja2 templates) |
| Database | SQLite |
| Authentication | bcrypt password hashing, email OTP (Gmail SMTP) |
| Excel files | openpyxl |

## Project structure

```
churn_project/
├── main.py                  # FastAPI app and all routes
├── auth.py                  # Users, OTP, login protection, report ownership
├── report_engine.py         # Data cleaning, prediction and offer engine
├── churn_model.pkl          # Trained model
├── metrics.json             # Model evaluation scores
├── expected_columns.json    # Required input columns
├── requirements.txt
├── .env.example             # Sample environment settings
├── templates/               # HTML pages
├── static/
│   ├── css/style.css
│   └── js/app.js
└── test_input.xlsx          # Sample file for testing
```

## Installation

**1. Clone the repository**

```bash
git clone https://github.com/Mamta-Rani26/churn-prediction.git
cd churn-prediction
```

**2. Create a virtual environment (recommended)**

```bash
python -m venv venv
venv\Scripts\activate        # Windows
source venv/bin/activate     # Mac / Linux
```

**3. Install the requirements**

```bash
pip install -r requirements.txt
```

> The model file was saved with a specific scikit-learn version. If the app fails to load `churn_model.pkl`, install the same version that was used for training.

**4. Create the `.env` file**

Copy `.env.example` to `.env` and fill in your values:

```
SECRET_KEY=put-a-long-random-string-here
SMTP_USER=yourname@gmail.com
SMTP_PASS=your16characterapppassword
```

- `SECRET_KEY`: any long random string, used to sign sessions
- `SMTP_USER` and `SMTP_PASS`: your Gmail address and a Gmail **App Password** (needs 2-Step Verification)
- If SMTP is not set, the OTP is printed in the terminal, which is handy for testing
- Add `HTTPS_ONLY=1` when the site is served over HTTPS

**5. Run the app**

```bash
uvicorn main:app --reload
```

Open http://127.0.0.1:8000/login in your browser.

## How to use

1. Register with your `@poornima.edu.in` email and verify it with the OTP sent to your inbox.
2. Sign in.
3. Download the Excel template, or use `test_input.xlsx` to try the app.
4. Upload the file (.xlsx, up to 5 MB) and click **Analyze customers**.
5. View the results and download the full report.

## Required Excel columns

`SeniorCitizen`, `Partner`, `Dependents`, `tenure`, `PhoneService`, `MultipleLines`, `InternetService`, `OnlineSecurity`, `OnlineBackup`, `DeviceProtection`, `TechSupport`, `StreamingTV`, `StreamingMovies`, `Contract`, `PaperlessBilling`, `PaymentMethod`, `MonthlyCharges`, `TotalCharges`

A `customerID` column is optional. It is shown in the results when present.

## Security

- CSRF token on every form, and logout works only through POST
- Only `@poornima.edu.in` email addresses can register
- Passwords are hashed with bcrypt and must have 8 to 72 characters, with at least one letter and one number
- OTP is stored hashed, expires in 10 minutes, allows 5 wrong attempts and has a 60 second resend cooldown
- Login is locked for 15 minutes after 5 wrong attempts
- Reports can be downloaded only by the user who created them, and are deleted after 24 hours
- Upload checks for file type, size, required columns and invalid values on the server
- Text starting with `=` in uploaded data is stored as plain text, never as an Excel formula
- Secrets are kept in `.env`, which is not uploaded to GitHub

## Limitations

- The model works with the columns listed above, so data in a different format needs to be mapped to them first.
- The login lockout is kept in memory and resets when the server restarts.
- Offer effects are estimated by the model, not measured in a real campaign.

## Future improvements

- Compare more models (Random Forest, XGBoost) and add explainability for each prediction
- Use a production database and a proper email service
- Add charts for trends over time and role-based access for admins

## Author

**Mamta Rani**
Final Year Project, Poornima University

- GitHub: [Mamta-Rani26](https://github.com/Mamta-Rani26)
- Email: 2024btechaidsmamta18486@poornima.edu.in

## License
This project was created for educational purposes.
