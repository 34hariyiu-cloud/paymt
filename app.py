
# app.py
# Streamlit Payments Dashboard with Data Cleaning
# Author: Sivaprakash (with Copilot assistance)

import io
import re
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
    Tries general parsing; if still NaT-heavy, attempts common explicit formats.
    """
    dt = pd.to_datetime(s, errors="coerce", dayfirst=dayfirst)

    # If too many NaT, try known patterns without raising exceptions.
    nat_ratio = dt.isna().mean()
    if nat_ratio > 0.5:
        # Try ISO-like first
        iso_try = pd.to_datetime(s, errors="coerce", format="%Y-%m-%d")
        dt = dt.fillna(iso_try)
        # Try day-first with dashes
        if dt.isna().any():
            df_try = pd.to_datetime(s, errors="coerce", format="%d-%m-%Y")
            dt = dt.fillna(df_try)
        # Try slashes
        if dt.isna().any():
            df_try2 = pd.to_datetime(s, errors="coerce", format="%d/%m/%Y")
            dt = dt.fillna(df_try2)

    return dt

def clean_amount_series(s: pd.Series) -> pd.Series:
    """
    Convert currency-like strings to numeric:
    - Removes non-numeric chars (₹, spaces, commas)
    - Keeps minus and decimal
    - Returns float with NaN for invalid
    """
    if s.dtype.kind in "fi":  # already numeric
        return s.astype(float)

    # Convert to string, strip currency and thousands separators
    cleaned = (
        s.astype(str)
         .str.replace(r"[₹, ]", "", regex=True)
         .str.replace(r"[^\d\.\-]", "", regex=True)  # keep digits, dot, minus
    )
    return pd.to_numeric(cleaned, errors="coerce")

def to_numeric_series(s: pd.Series) -> pd.Series:
    """Coerce to numeric with NaN for invalid entries."""
    return pd.to_numeric(s, errors="coerce")

def normalize_status_series(s: pd.Series) -> pd.Series:
    """
    Normalize status values into a tidy set: paid / pending / cancelled / other.
    Uses keyword matching; keeps original when unknown.
    """
    s2 = s.astype(str).str.strip().str.lower()
    def normalize(x: str) -> str:
        if any(k in x for k in ["paid", "settled", "complete", "completed", "closed", "success"]):
            return "paid"
        if any(k in x for k in ["unpaid", "due", "pending", "await", "open", "outstanding"]):
            return "pending"
        if any(k in x for k in ["cancel", "void", "reversed", "failed"]):
            return "cancelled"
        return x  # leave as-is for custom states
    return s2.apply(normalize)

def compute_amounts(
    df: pd.DataFrame,
    amount_col: str,
    amount_paid_col: Optional[str] = None,
    outstanding_col: Optional[str] = None,
    status_col: Optional[str] = None
) -> Tuple[float, float, float]:
    """
    Compute total amount, amount paid, and outstanding based on available columns.
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
    elif status_col and status_col in df.columns:
        status_norm = normalize_status_series(df[status_col])
        paid_mask = status_norm.eq("paid")
        amount_paid = to_numeric_series(df.loc[paid_mask, amount_col]).sum()
        outstanding = total_amount - amount_paid
    else:
        outstanding = total_amount  # assume nothing paid if not tracked

    return float(total_amount), float(amount_paid), float(outstanding)

def read_uploaded_file(uploaded_file) -> pd.DataFrame:
    """
    Robust reader: CSV / XLSX / XLS.
    Detect CSV delimiter when file loads as single column.
    """
    fname = uploaded_file.name.lower()
    data_bytes = uploaded_file.getvalue()
    bio = io.BytesIO(data_bytes)

    try:
        if fname.endswith(".csv"):
            # First attempt with default
            df = pd.read_csv(bio)
            # If single col and likely semicolon-separated, re-read with sep=';'
            if df.shape[1] == 1:
                bio.seek(0)
                df_alt = pd.read_csv(bio, sep=";")
                if df_alt.shape[1] > 1:
                    df = df_alt
        elif fname.endswith(".xlsx"):
            df = pd.read_excel(bio, engine="openpyxl")
        elif fname.endswith(".xls"):
            df = pd.read_excel(bio, engine="xlrd")
        else:
            raise ValueError("Unsupported file type. Please upload a .csv, .xlsx, or .xls file.")
    except Exception as e:
        raise RuntimeError(f"Failed to read file: {e}")
    return df

def trim_string_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Strip leading/trailing whitespace in all object/string columns."""
    out = df.copy()
    str_cols = out.select_dtypes(include=["object", "string"]).columns
    for c in str_cols:
        out[c] = out[c].astype(str).str.strip()
    return out

def deduplicate_rows(df: pd.DataFrame,
                     invoice_id_col: Optional[str],
                     date_col: Optional[str],
                     amount_col: Optional[str],
                     status_col: Optional[str]) -> Tuple[pd.DataFrame, int]:
    """
    Deduplicate:
      - Prefer invoice_id if provided
      - Else use [date, amount, status] when available
    Returns (deduped_df, removed_count)
    """
    before = len(df)
    out = df.copy()

    if invoice_id_col and invoice_id_col in out.columns:
        out = out.drop_duplicates(subset=[invoice_id_col], keep="first")
    else:
        subset = [c for c in [date_col, amount_col, status_col] if c and c in out.columns]
        if subset:
            out = out.drop_duplicates(subset=subset, keep="first")
        else:
            out = out.drop_duplicates(keep="first")

    removed = before - len(out)
    return out, removed

# -----------------------------
# Sidebar: Data Input & Mapping
# -----------------------------
st.sidebar.header("📄 Data source")
uploaded_file = st.sidebar.file_uploader(
    "Upload a CSV or Excel invoice file",
    type=["csv", "xlsx", "xls"],
    help="Include columns for amount, status/paid/outstanding, and optionally date/invoice id."
)

st.sidebar.header("🧼 Data cleaning options")
dayfirst = st.sidebar.checkbox("Parse dates as day-first (DD-MM-YYYY)", value=False)
apply_trim = st.sidebar.checkbox("Trim whitespace in text columns", value=True)
normalize_status_opt = st.sidebar.checkbox("Normalize status values (paid/pending/cancelled)", value=True)
dedup_opt = st.sidebar.checkbox("Remove duplicate rows", value=True)
drop_invalid_amount_opt = st.sidebar.checkbox("Drop rows with invalid/non-positive amount", value=True)
clean_currency_opt = st.sidebar.checkbox("Convert currency-like amounts to numeric", value=True)

st.sidebar.header("🔠 Column mapping")
st.sidebar.caption("Map your file's columns to the expected fields (case-sensitive).")

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
    df_raw = read_uploaded_file(uploaded_file)
except Exception as e:
    st.error(str(e))
    st.stop()

# Validate required amount column
if amount_col not in df_raw.columns:
    st.error(f"Amount column '{amount_col}' not found in uploaded file. Please correct the mapping in the sidebar.")
    st.stop()

# -----------------------------
# Cleaning Pipeline
# -----------------------------
df = df_raw.copy()
rows_before = len(df)

# 1) Trim strings
if apply_trim:
    df = trim_string_columns(df)

# 2) Clean numeric-like amounts
if clean_currency_opt:
    df[amount_col] = clean_amount_series(df[amount_col])
    if amount_paid_col and amount_paid_col in df.columns:
        df[amount_paid_col] = clean_amount_series(df[amount_paid_col])
    if outstanding_col and outstanding_col in df.columns:
        df[outstanding_col] = clean_amount_series(df[outstanding_col])
else:
    df[amount_col] = to_numeric_series(df[amount_col])
    if amount_paid_col and amount_paid_col in df.columns:
        df[amount_paid_col] = to_numeric_series(df[amount_paid_col])
    if outstanding_col and outstanding_col in df.columns:
        df[outstanding_col] = to_numeric_series(df[outstanding_col])

# 3) Parse date
if date_col and date_col in df.columns:
    df[date_col] = parse_date_series(df[date_col], dayfirst=dayfirst)

# 4) Normalize status
if normalize_status_opt and status_col and status_col in df.columns:
    df[status_col] = normalize_status_series(df[status_col])

# 5) Drop invalid/non-positive amount rows
dropped_invalid_amount = 0
if drop_invalid_amount_opt:
    invalid_mask = df[amount_col].isna() | (df[amount_col] <= 0)
    dropped_invalid_amount = int(invalid_mask.sum())
    df = df.loc[~invalid_mask].copy()

# 6) Deduplicate
removed_dupes = 0
if dedup_opt:
    df, removed_dupes = deduplicate_rows(df, invoice_id_col, date_col, amount_col, status_col)

rows_after = len(df)
rows_removed = rows_before - rows_after

# Summary panel
st.subheader("🧼 Cleaning summary")
c1, c2, c3, c4 = st.columns(4)
with c1:
    st.metric("Rows (before)", rows_before)
with c2:
    st.metric("Invalid amount rows dropped", dropped_invalid_amount)
with c3:
    st.metric("Duplicates removed", removed_dupes)
with c4:
    st.metric("Rows (after)", rows_after)

st.caption("Tip: Adjust cleaning options in the sidebar to change how data is processed.")

st.divider()

# -----------------------------
# Filters (Date)
# -----------------------------
fdf = df.copy()
if date_col and date_col in fdf.columns and fdf[date_col].notna().any():
    st.subheader("🔍 Filters")
    min_date = pd.to_datetime(fdf[date_col], errors="coerce").min()
    max_date = pd.to_datetime(fdf[date_col], errors="coerce").max()
    if pd.notna(min_date) and pd.notna(max_date):
        start_date, end_date = st.slider(
            "Date range",
            min_value=min_date.to_pydatetime(),
            max_value=max_date.to_pydatetime(),
            value=(min_date.to_pydatetime(), max_date.to_pydatetime()),
            format="YYYY-MM-DD",
            help="Use the slider to filter invoices by date."
        )
        mask = (fdf[date_col] >= pd.to_datetime(start_date)) & (fdf[date_col] <= pd.to_datetime(end_date))
        fdf = fdf.loc[mask].copy()

# -----------------------------
# KPI cards
# -----------------------------
total_amount, amount_paid, outstanding = compute_amounts(
    fdf,
    amount_col=amount_col,
    amount_paid_col=amount_paid_col if amount_paid_col in fdf.columns else None,
    outstanding_col=outstanding_col if outstanding_col in fdf.columns else None,
    status_col=status_col if status_col in fdf.columns else None
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

# -----------------------------
# Table & Download
# -----------------------------
st.subheader("📊 Cleaned invoices")
st.dataframe(fdf, use_container_width=True)

# Download cleaned CSV (filtered)
csv_bytes = fdf.to_csv(index=False).encode("utf-8")
st.download_button(
    label="⬇️ Download cleaned & filtered CSV",
    data=csv_bytes,
    file_name="cleaned_invoices.csv",
    mime="text/csv"
)

# Optional: monthly totals chart
if date_col and date_col in fdf.columns and fdf[date_col].notna().any():
    st.subheader("📈 Monthly totals")
    monthly = (
        fdf.dropna(subset=[date_col])
           .assign(month=lambda x: x[date_col].dt.to_period("M").dt.to_timestamp())
           .groupby("month", as_index=False)[amount_col].sum()
           .sort_values("month")
    )
    st.line_chart(monthly.set_index("month")[amount_col], use_container_width=True)

# Footer
st.caption(
    "Configured columns: "
    f"amount='{amount_col}', amount_paid='{amount_paid_col}', outstanding='{outstanding_col}', "
    f"date='{date_col}', invoice_id='{invoice_id_col}', status='{status_col}'."
)
