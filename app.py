
# app.py
# Streamlit Payments Dashboard - Clean version
# Includes INR formatting, safe date parsing (no deprecated infer_datetime_format),
# KPI cards, file upload, and a monthly totals chart.
# Author: Sivaprakash (with Copilot assistance)

import math
from typing import Optional, Tuple

import pandas as pd
import streamlit as st

# -----------------------------
# Page Setup
# -----------------------------
st.set_page_config(page_title="Payments Dashboard", page_icon="💵", layout="wide")

# -----------------------------
# Helpers
# -----------------------------

def inr(value) -> str:
    """
    Format a numeric value as Indian Rupees with Indian-digit grouping.
    Example: 1234567.8 -> ₹12,34,567.80
    Handles None/NaN gracefully by returning "₹0.00".
    """
    try:
        if value is None:
            return "₹0.00"
        # Handle pandas NA/NaN
        if isinstance(value, float) and math.isnan(value):
            return "₹0.00"
        val = float(value)
    except Exception:
        return "₹0.00"

    s = f"{abs(val):.2f}"
    whole, frac = s.split(".")
    # Indian-style digit grouping (last 3 digits, then groups of 2)
    if len(whole) > 3:
        prefix = whole[:-3]
        last3 = whole[-3:]
        grouped = ""
        while len(prefix) > 2:
            grouped = "," + prefix[-2:] + grouped
            prefix = prefix[:-2]
        if prefix:
            grouped = prefix + grouped
        whole = grouped + "," + last3
    sign = "-" if val < 0 else ""
    return f"{sign}₹{whole}.{frac}"

def parse_date_series(s: pd.Series, dayfirst: bool = False) -> pd.Series:
    """
    Safe date parsing that avoids deprecated 'infer_datetime_format'.
    If you know your date format explicitly, prefer passing format=... to pd.to_datetime.
    """
    # Primary attempt—robust general parser
    dt = pd.to_datetime(s, errors="coerce", dayfirst=dayfirst)
    return dt

def to_numeric_series(s: pd.Series) -> pd.Series:
    """Convert a series to numeric safely (NaN for invalid)."""
    return pd.to_numeric(s, errors="coerce")

def compute_amounts(
    df: pd.DataFrame,
    amount_col: str,
    amount_paid_col: Optional[str] = None,
    outstanding_col: Optional[str] = None
) -> Tuple[float, float, float]:
    """
    Compute total amount, amount paid, and outstanding based on available columns.

    Priority:
      - If amount_paid_col is provided and exists → use it.
      - Else if outstanding_col exists → outstanding = sum(outstanding), paid = total - outstanding.
      - Else if there is a boolean/text 'status' paid indicator → paid = sum(amount for status == 'Paid').
      - Else assume paid = 0 and outstanding = total.
    """
    total_amount = to_numeric_series(df[amount_col]).sum()

    amount_paid = 0.0
    outstanding = None

    if amount_paid_col and amount_paid_col in df.columns:
        amount_paid = to_numeric_series(df[amount_paid_col]).sum()
        outstanding = total_amount - amount_paid
    elif outstanding_col and outstanding_col in df.columns:
        outstanding = to_numeric_series(df[outstanding_col]).sum()
        amount_paid = total_amount - outstanding
    elif "status" in df.columns:
        status_col = df["status"].astype(str).str.lower()
        paid_mask = status_col.isin(["paid", "complete", "completed", "settled"])
        amount_paid = to_numeric_series(df.loc[paid_mask, amount_col]).sum()
        outstanding = total_amount - amount_paid
    else:
        outstanding = total_amount  # assume nothing paid if not tracked

    return float(total_amount), float(amount_paid), float(outstanding)

# -----------------------------
# Sidebar: Data Input & Mapping
# -----------------------------
st.sidebar.header("📄 Data source")
uploaded_file = st.sidebar.file_uploader(
    "Upload a CSV or Excel invoice file",
    type=["csv", "xlsx", "xls"],
    help="Include columns for amount, optional paid/outstanding, and optionally date."
)

dayfirst = st.sidebar.checkbox("Parse dates as day-first (DD-MM-YYYY)", value=False)

st.sidebar.header("🔠 Column mapping")
st.sidebar.caption("Map your file's columns to the expected fields.")

amount_col = st.sidebar.text_input("Amount column name", value="amount")
amount_paid_col = st.sidebar.text_input("Amount paid column name (optional)", value="amount_paid")
outstanding_col = st.sidebar.text_input("Outstanding column name (optional)", value="outstanding")
date_col = st.sidebar.text_input("Date column name (optional)", value="date")
invoice_id_col = st.sidebar.text_input("Invoice ID column name (optional)", value="invoice_id")
status_col = st.sidebar.text_input("Status column name (optional)", value="status")

# -----------------------------
# Main App
# -----------------------------
st.title("💵 Payments Dashboard")

if not uploaded_file:
    st.info("Upload a CSV/Excel file to continue.")
    st.stop()

# Load data
try:
    fname = uploaded_file.name.lower()
    if fname.endswith(".csv"):
        df = pd.read_csv(uploaded_file)
    elif fname.endswith(".xlsx"):
        df = pd.read_excel(uploaded_file, engine="openpyxl")
    elif fname.endswith(".xls"):
        df = pd.read_excel(uploaded_file, engine="xlrd")
    else:
        st.error("Unsupported file type. Please upload a .csv, .xlsx, or .xls file.")
        st.stop()
except Exception as e:
    st.error(f"Failed to read file: {e}")
    st.stop()

# Validate required amount column
if amount_col not in df.columns:
    st.error(f"Amount column '{amount_col}' not found in uploaded file. Please correct the mapping in the sidebar.")
    st.stop()

# Clean and parse
df = df.copy()

# Coerce amount columns to numeric
df[amount_col] = to_numeric_series(df[amount_col])

if amount_paid_col and amount_paid_col in df.columns:
    df[amount_paid_col] = to_numeric_series(df[amount_paid_col])

if outstanding_col and outstanding_col in df.columns:
    df[outstanding_col] = to_numeric_series(df[outstanding_col])

# Parse date if present
if date_col and date_col in df.columns:
    df[date_col] = parse_date_series(df[date_col], dayfirst=dayfirst)

# Top filters: Date range (if date available)
if date_col in df.columns:
    st.subheader("🔍 Filters")
    min_date = pd.to_datetime(df[date_col], errors="coerce").min()
    max_date = pd.to_datetime(df[date_col], errors="coerce").max()
    if pd.notna(min_date) and pd.notna(max_date):
        start_date, end_date = st.slider(
            "Date range",
            min_value=min_date.to_pydatetime(),
            max_value=max_date.to_pydatetime(),
            value=(min_date.to_pydatetime(), max_date.to_pydatetime()),
            format="YYYY-MM-DD",
            help="Use the slider to filter invoices by date."
        )
        mask = (df[date_col] >= pd.to_datetime(start_date)) & (df[date_col] <= pd.to_datetime(end_date))
        fdf = df.loc[mask].copy()
    else:
        fdf = df.copy()
else:
    fdf = df.copy()

# KPI cards
total_amount, amount_paid, outstanding = compute_amounts(
    fdf,
    amount_col=amount_col,
    amount_paid_col=amount_paid_col if amount_paid_col in fdf.columns else None,
    outstanding_col=outstanding_col if outstanding_col in fdf.columns else None
)

k1, k2, k3 = st.columns(3)
with k1:
    st.subheader("Total amount")
    st.markdown(f"**{inr(total_amount)}**")
    st.caption(f"(from {len(fdf)} invoices)")
with k2:
    st.subheader("Amount paid")
    st.markdown(f"**{inr(amount_paid)}**")
with k3:
    st.subheader("Outstanding")
    st.markdown(f"**{inr(outstanding)}**")

st.divider()

# Table preview
st.subheader("📊 Invoices")
st.dataframe(fdf if len(fdf) else df, use_container_width=True)

# Optional: simple monthly totals chart if date is available
if date_col in fdf.columns and fdf[date_col].notna().any():
    st.subheader("📈 Monthly totals")
    monthly = (
        fdf.dropna(subset=[date_col])
           .assign(month=lambda x: x[date_col].dt.to_period("M").dt.to_timestamp())
           .groupby("month", as_index=False)[amount_col].sum()
           .sort_values("month")
    )
    st.line_chart(
        monthly.set_index("month")[amount_col],
        use_container_width=True
    )

# Notes / Footer
st.caption(
    "Tip: Ensure your file includes clear numeric columns for "
    f"'{amount_col}', optional '{amount_paid_col}', '{outstanding_col}', and a date column '{date_col}' if available."
)
