import numpy as np
import pandas as pd
 
 
def make_offer(cond, changes=None, discount=1.0):
    def apply(d):
        elig = cond(d)
        d2 = d.copy()
        for col, val in (changes or {}).items():
            d2.loc[elig, col] = val
        d2.loc[elig, "MonthlyCharges"] = d2.loc[elig, "MonthlyCharges"] * discount
        return d2, elig
    return apply
 
 
has_net = lambda d: d["InternetService"] != "No"
 
offers = {
    "1-year contract + 10% discount": make_offer(
        lambda d: d["Contract"] == "Month-to-month", {"Contract": "One year"}, 0.90),
    "2-year contract + 15% discount": make_offer(
        lambda d: d["Contract"] != "Two year", {"Contract": "Two year"}, 0.85),
    "Free tech support (6 months)": make_offer(
        lambda d: has_net(d) & (d["TechSupport"] == "No"), {"TechSupport": "Yes"}),
    "Free online security (6 months)": make_offer(
        lambda d: has_net(d) & (d["OnlineSecurity"] == "No"), {"OnlineSecurity": "Yes"}),
    "Autopay incentive": make_offer(
        lambda d: d["PaymentMethod"].isin(["Electronic check", "Mailed check"]),
        {"PaymentMethod": "Bank transfer (automatic)"}),
    "15% bill discount": make_offer(lambda d: d["MonthlyCharges"] > 0, None, 0.85),
}
 
 
NUM_COLS = ["tenure", "MonthlyCharges", "TotalCharges"]
CAT_COLS = ["Partner", "Dependents", "PhoneService", "MultipleLines",
            "InternetService", "OnlineSecurity", "OnlineBackup",
            "DeviceProtection", "TechSupport", "StreamingTV",
            "StreamingMovies", "Contract", "PaperlessBilling", "PaymentMethod"]
 
 
def clean_features(raw, expected_cols):
    """Makes HR data safe for the model: fixes dtypes, spaces and case."""
    feats = raw[expected_cols].copy()
 
    # numeric columns -> always float (int columns break the offer discount step)
    for c in NUM_COLS:
        feats[c] = pd.to_numeric(feats[c], errors="coerce")
    bad = feats[["tenure", "MonthlyCharges"]].isna().any(axis=1)
    if bad.any():
        rows = (bad[bad].index[:5] + 2).tolist()   # +2 = Excel row number
        raise ValueError(f"tenure/MonthlyCharges missing or not a number (Excel rows {rows})")
    feats["TotalCharges"] = feats["TotalCharges"].fillna(0)
    feats[NUM_COLS] = feats[NUM_COLS].astype(float)
 
    # SeniorCitizen: accept 0/1, Yes/No, True/False
    sc = feats["SeniorCitizen"].astype(str).str.strip().str.lower()
    feats["SeniorCitizen"] = sc.map({"1": 1, "1.0": 1, "yes": 1, "true": 1,
                                     "0": 0, "0.0": 0, "no": 0, "false": 0}).fillna(0).astype(int)
 
    # text columns: trim spaces and match the exact spelling the model knows
    canon = {"yes": "Yes", "no": "No", "no phone service": "No phone service",
             "no internet service": "No internet service", "dsl": "DSL",
             "fiber optic": "Fiber optic", "month-to-month": "Month-to-month",
             "one year": "One year", "two year": "Two year",
             "electronic check": "Electronic check", "mailed check": "Mailed check",
             "bank transfer (automatic)": "Bank transfer (automatic)",
             "credit card (automatic)": "Credit card (automatic)"}
    for c in CAT_COLS:
        t = feats[c].astype(str).str.strip()
        feats[c] = t.str.lower().map(canon).fillna(t).astype(object)
    return feats
 
 
def build_report(raw, model, expected_cols):
    feats = clean_features(raw, expected_cols)
 
    base = model.predict_proba(feats)[:, 1]
    best_prob = base.copy()
    best_offer = np.array(["No offer needed"] * len(feats), dtype=object)
 
    for name, fn in offers.items():
        modified, elig = fn(feats)
        new_prob = model.predict_proba(modified)[:, 1]
        better = elig.values & (new_prob < best_prob)
        best_prob = np.where(better, new_prob, best_prob)
        best_offer = np.where(better, name, best_offer)
 
    risk = np.where(base >= 0.6, "High", np.where(base >= 0.3, "Medium", "Low"))
    low = risk == "Low"
    best_offer[low] = "No offer needed"
    best_prob[low] = base[low]
 
    out = raw.copy()
    out["churn_probability_%"] = (base * 100).round(1)
    out["risk_level"] = risk
    out["recommended_offer"] = best_offer
    out["probability_after_offer_%"] = (best_prob * 100).round(1)
    return out