
# app.py
"""
Payments Totals — Streamlit app
- Robust Excel date parsing (handles Excel serial numbers like 45413)
- Filters by Invoice Date + optional Payment Status
- KPIs: Total amount (Σ Invoice value), Amount paid (Σ Amount Paid), Amount to pay (Total − Paid)
- Bank totals KPIs (by labels)
- Vendor summary (amount to pay)
- Bank summary (4 rows: HDFC CA label, HDFC OD, Kotak OD, Others)
- Export (Excel): Filtered, VendorSummary, BankTotals, BankSummary
"""

import io
import numpy as np
import pandas as pd
import streamlit as st

# -------------------- UI config --------------------
st.set_page_config(page_title="Payments Totals", layout="wide")
st.title("Payments Totals")
st.write("Pick **Start date** and **End date** by **Invoice Date**. We show:")
st.markdown(
    """
    - **Total amount** (Σ Invoice Value)
    - **Amount paid** (Σ Amount Paid)
    - **Amount to pay** (Total − Paid)
    """
)

# -------------------- Helpers --------------------
@st.cache_data
def read_excel_bytes(file_bytes: bytes, sheet_name=None, filename: str | None = None) -> pd.DataFrame | dict:
    """
    Read Excel robustly:
    - .xlsx → openpyxl
    - .xls  → xlrd (optional; add to requirements.txt if needed)
    Shows a friendly error if dependencies are missing.
    Returns either a DataFrame or a dict of DataFrames if sheet_name=None and workbook has multiple sheets.
    """
    if file_bytes is None:
        st.error("Please upload an Excel file in the sidebar.")
        st.stop()

    buf = io.BytesIO(file_bytes)

    # Choose engine using filename; default to openpyxl
    engine = "openpyxl"
    if filename and filename.lower().endswith(".xls"):
        engine = "xlrd"

    # Dependency check
    try:
        if engine == "openpyxl":
            import openpyxl  # noqa: F401
        else:
            import xlrd      # noqa: F401
    except ImportError as e:
        st.error(
            f"Missing Excel dependency: {e}. "
            "Update requirements.txt (include openpyxl for .xlsx, xlrd for .xls) and redeploy."
        )
        st.stop()

    return pd.read_excel(buf, sheet_name=sheet_name, engine=engine)


def parse_excel_or_text_date(series: pd.Series) -> pd.Series:
    """
    Convert mixed date series:
    - If values are mostly numeric → treat as Excel serial dates (origin=1899-12-30).
    - Otherwise, parse as text dates.
    """
    numeric = pd.to_numeric(series, errors="coerce")
    numeric_ratio = numeric.notna().mean()
    if numeric_ratio >= 0.6:  # majority numeric → Excel serials
        return pd.to_datetime(numeric, origin="1899-12-30", unit="D", errors="coerce")
    return pd.to_datetime(series, errors="coerce", infer_datetime_format=True)


def inr(x: float) -> str:
    """Format as ₹ currency."""
    try:
        return f"₹{float(x):,.2f}"
    except Exception:
        return "₹0.00"


def contains_match(series: pd.Series, label: str) -> pd.Series:
    """Case-insensitive 'contains' match."""
    s = series.astype(str).str.lower()
    return s.str.contains(str(label).lower(), na=False)


def exact_match(series: pd.Series, label: str) -> pd.Series:
    """Exact match after trimming."""
    s = series.astype(str).str.strip()
    return s == str(label).strip()


# -------------------- Sidebar: data source --------------------
with st.sidebar:
    st.header("Load your data")
    uploaded = st.file_uploader("Upload Excel (.xlsx or .xls)", type=["xlsx", "xls"])
    sheet = st.text_input("Sheet name (optional)")
    debug_mode = st.toggle("Debug bank summary", value=False)

# Get file bytes (require upload on cloud)
file_bytes = None
source_text = None
if uploaded is not None:
    file_bytes = uploaded.getvalue()
    source_text = f"Uploaded: {uploaded.name}"
else:
    source_text = "Upload an Excel file using the sidebar."
st.caption(source_text)

# Stop if no file (prevents downstream errors)
if file_bytes is None:
    st.info("Please upload an Excel file to proceed.")
    st.stop()

# Read workbook (support multi-sheet)
raw = read_excel_bytes(file_bytes, sheet_name=(sheet or None), filename=(uploaded.name if uploaded else None))
if isinstance(raw, dict):
    names = list(raw.keys())
    with st.sidebar:
        chosen = st.selectbox("Choose sheet", options=names)
    df = raw[chosen]
else:
    df = raw

if df is None or df.empty:
    st.error("Selected sheet appears empty.")
    st.stop()

orig_cols = list(df.columns)

# -------------------- Column mapping (defaults to common headers) --------------------
with st.sidebar:
    st.header("Map columns")
    def pick(label, default):
        idx = orig_cols.index(default) if default in orig_cols else 0
        return st.selectbox(label, orig_cols, index=idx)

    # Adjust defaults to match your file names if needed:
    invoice_date_col  = pick("Invoice Date", "Invoice date")
    vendor_col        = pick("Vendor", "Vendor Name")
    invoice_value_col = pick("Invoice Value (total)", "Invoice value")
    amount_paid_col   = pick("Amount Paid", "Amount Paid")
    status_col        = pick("Payment Status", "Payment Status")
    bank_col          = pick("Bank", "Bank Name")

# -------------------- Prepare & clean --------------------
work = df.copy()

# Robust date parsing for Excel serials & text dates
work[invoice_date_col] = parse_excel_or_text_date(work[invoice_date_col])

# Coerce numerics defensively
for c in [invoice_value_col, amount_paid_col]:
    work[c] = pd.to_numeric(work[c], errors="coerce").fillna(0)

# Normalize status (handle 'Paid', 'unPaid', 'unpaid', 'Pending', etc.)
if status_col in work.columns:
    s = work[status_col].astype(str).str.strip().str.lower()
    norm = s.replace({"paid": "Paid", "unpaid": "Unpaid", "unpaid ": "Unpaid", "pending": "Pending"})
    work["_StatusNorm"] = norm
else:
    work["_StatusNorm"] = "Unknown"

# -------------------- Filters --------------------
min_d = pd.to_datetime(work[invoice_date_col]).min()
max_d = pd.to_datetime(work[invoice_date_col]).max()
if pd.isna(min_d) or pd.isna(max_d):
    min_d = pd.Timestamp.today() - pd.Timedelta(days=365)
    max_d = pd.Timestamp.today()

c1, c2, c3 = st.columns([1, 1, 1])
with c1:
    start_date = st.date_input("Start date", value=min_d.date(), format="MM/DD/YYYY")
with c2:
    end_date = st.date_input("End date", value=max_d.date(), format="MM/DD/YYYY")
with c3:
    if st.button("Reset"):
        start_date = min_d.date()
        end_date = max_d.date()

with st.sidebar:
    status_choice = st.selectbox(
        "Payment status (optional)", options=["All", "Paid", "Unpaid", "Pending"], index=0
    )

# Safe filter using .between()
start_ts = pd.to_datetime(start_date)
end_ts   = pd.to_datetime(end_date)

dt_series = pd.to_datetime(work[invoice_date_col], errors="coerce")
date_mask = dt_series.between(start_ts, end_ts, inclusive="both")

status_mask = pd.Series(True, index=work.index)
if status_choice != "All":
    status_mask = (work["_StatusNorm"] == status_choice)

fdf = work.loc[date_mask & status_mask].copy()

# -------------------- Debug hints --------------------
if debug_mode:
    st.info(f"DEBUG → filtered rows: {len(fdf)} | map → bank_col='{bank_col}', invoice_value_col='{invoice_value_col}', amount_paid_col='{amount_paid_col}'")
    try:
        distinct_banks = sorted(fdf[bank_col].dropna().astype(str).str.strip().unique().tolist())
        st.caption(f"DEBUG → first banks: {distinct_banks[:10]}")
    except Exception as e:
        st.caption(f"DEBUG → cannot list banks: {e}")

# -------------------- Global KPIs --------------------
total_amount = float(np.nansum(fdf[invoice_value_col]))
amount_paid  = float(np.nansum(fdf[amount_paid_col]))
amount_to_pay = total_amount - amount_paid

k1, k2, k3 = st.columns(3)
with k1:
    st.subheader("Total amount")
    st.markdown(f"**{inr(total_amount)}**")
    st.caption(f"(from {len(fdf)} invoices)")
with k2:
    st.subheader("Amount paid")
    st.markdown(f"**{inr(amount_paid)}**")
with k3:
    st.subheader("Amount to pay")
    st.markdown(f"**{inr(amount_to_pay)}**")

# -------------------- Bank totals (labels) --------------------
st.markdown("### Bank totals (Σ Invoice Value by Bank label)")
with st.sidebar:
    st.header("Bank settings")
    # Defaults commonly used in your data; change as needed in UI
    hdfc_ca_label = st.text_input("Bank name for HDFC CA", value="HDFC CA - 87975")
    hdfc_od_label = st.text_input("Bank name for HDFC OD", value="HDFC OD")
    kotak_label   = st.text_input("Bank name for Kotak OD", value="Kotak OD")
    match_mode    = st.radio("Match mode", ["Exact", "Contains"], index=1)  # default Contains

def bank_mask(df: pd.DataFrame, label: str) -> pd.Series:
    return exact_match(df[bank_col], label) if match_mode == "Exact" else contains_match(df[bank_col], label)

def bank_sum(df: pd.DataFrame, label: str) -> float:
    rows = df.loc[bank_mask(df, label), invoice_value_col]
    return float(rows.sum())

hdfc_ca_total = bank_sum(fdf, hdfc_ca_label)
hdfc_od_total = bank_sum(fdf, hdfc_od_label)
kotak_total   = bank_sum(fdf, kotak_label)

sum_three = hdfc_ca_total + hdfc_od_total + kotak_total
b1, b2, b3, b4 = st.columns(4)
with b1:
    st.metric(f"{hdfc_ca_label} TOTAL", inr(hdfc_ca_total))
with b2:
    st.metric(f"{hdfc_od_label} TOTAL", inr(hdfc_od_total))
with b3:
    st.metric(f"{kotak_label} TOTAL", inr(kotak_total))
with b4:
    st.metric("Sum of three", inr(sum_three))

# Reconciliation note + others total by complement
m_ca    = bank_mask(fdf, hdfc_ca_label)
m_od    = bank_mask(fdf, hdfc_od_label)
m_kotak = bank_mask(fdf, kotak_label)
m_three = m_ca | m_od | m_kotak

others_total_amount = float(fdf.loc[~m_three, invoice_value_col].sum())
if abs(sum_three - total_amount) < 0.005:
    st.success("✔️ Sum of the three bank totals equals the Total amount KPI.")
else:
    st.warning(
        f"⚠️ Sum of three = {inr(sum_three)} vs Total amount = {inr(total_amount)}. "
        f"Remaining (other banks) = {inr(others_total_amount)}."
    )

# -------------------- Vendor summary (amount to pay) --------------------
st.markdown("### Vendor summary (amount to pay)")
st.caption("Shows how much is pending per vendor in the selected date range.")

vendor_agg = fdf.groupby(vendor_col).agg(
    Invoices=(vendor_col, "size"),
    TotalAmount=(invoice_value_col, "sum"),
    AmountPaid=(amount_paid_col, "sum"),
).reset_index()
vendor_agg["AmountToPay"] = vendor_agg["TotalAmount"] - vendor_agg["AmountPaid"]

# Pretty table (₹ formatting for vendor view)
show_vendor = vendor_agg.copy()
for c in ["TotalAmount", "AmountPaid", "AmountToPay"]:
    show_vendor[c] = show_vendor[c].apply(inr)

st.dataframe(
    show_vendor.rename(columns={
        vendor_col: "Vendor",
        "Invoices": "Invoices",
        "TotalAmount": "Total amount (₹)",
        "AmountPaid": "Amount paid (₹)",
        "AmountToPay": "Amount to pay (₹)",
    }),
    use_container_width=True,
)

# -------------------- Bank Summary (4 rows: HDFC CA, HDFC OD, Kotak OD, Others) --------------------
st.markdown("### Bank summary")

def summary_row(df: pd.DataFrame, label: str, mask_series: pd.Series) -> dict:
    txns = int(mask_series.sum())
    total = float(df.loc[mask_series, invoice_value_col].sum())
    paid  = float(df.loc[mask_series, amount_paid_col].sum())
    amt_to_pay = total - paid
    return {
        "Bank Name": label,
        "Txns": txns,
        "TotalAmount": total,
        "AmountToPay": amt_to_pay,
        "PaidAmount": paid,
        "Outstanding": amt_to_pay,
    }

m_others = ~m_three
rows = [
    summary_row(fdf, hdfc_ca_label, m_ca),
    summary_row(fdf, hdfc_od_label, m_od),
    summary_row(fdf, kotak_label,   m_kotak),
    summary_row(fdf, "Others",       m_others),
]
bank_summary_df = pd.DataFrame(rows)

# Keep for export and render (raw numbers to match screenshot style)
st.session_state["bank_summary_df"] = bank_summary_df.copy()
st.dataframe(bank_summary_df, use_container_width=True, height=240)

# -------------------- Export --------------------
