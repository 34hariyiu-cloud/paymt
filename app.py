
# app.py
import streamlit as st
import pandas as pd
from datetime import date

st.set_page_config(page_title="Payments Totals - Bank Breakdown", layout="wide")

# Expected columns
EXPECTED_COLS = [
    'Bank Name', 'Payment mode', 'Due date', 'Payment Date', 'Vendor Name',
    'Invoice number', 'Invoice date', 'Invoice value', 'TDS',
    'Amount Paid', 'UTR no.', 'Payment status'
]

# ---------------- Helper Functions ----------------

def load_excel_fix_headers(path: str) -> pd.DataFrame:
    """Load Excel and normalize headers."""
    df = pd.read_excel(path, engine="openpyxl", header=None)
    first_row = df.iloc[0].astype(str).tolist()
    if 'Bank Name' in first_row:
        df = df.iloc[1:].reset_index(drop=True)
        df.columns = EXPECTED_COLS
    else:
        df.columns = EXPECTED_COLS
    return df

def coerce_dates(df: pd.DataFrame) -> pd.DataFrame:
    """Convert date columns to datetime."""
    for c in ['Due date', 'Payment Date', 'Invoice date']:
        if c in df.columns:
            df[c] = pd.to_datetime(df[c], errors='coerce')
            if pd.api.types.is_datetime64tz_dtype(df[c]):
                df[c] = df[c].dt.tz_localize(None)
    return df

def filter_by_invoice_date(df: pd.DataFrame, start_dt: date, end_dt: date, date_col: str = 'Invoice date') -> pd.DataFrame:
    """Filter rows by inclusive date range."""
    start_ts = pd.to_datetime(start_dt)
    end_ts = pd.to_datetime(end_dt) + pd.Timedelta(days=1) - pd.Timedelta(microseconds=1)
    ser = df[date_col]
    mask = ser.notna() & (ser >= start_ts) & (ser <= end_ts)
    return df.loc[mask].copy()

def to_excel_bytes(df_out: pd.DataFrame) -> bytes:
    """Convert DataFrame to Excel bytes for download."""
    with pd.ExcelWriter("filtered_output.xlsx", engine="openpyxl") as writer:
        df_out.to_excel(writer, index=False, sheet_name="Filtered")
    with open("filtered_output.xlsx", "rb") as f:
        return f.read()

# ---------------- UI ----------------

st.title("💳 Payments Totals – Bank Breakdown")
st.caption("Reading data from Book10.xlsx (place this file next to app.py).")

# Load data
default_path = "Book10.xlsx"
try:
    df = load_excel_fix_headers(default_path)
except FileNotFoundError:
    st.error("❌ File not found. Please place Book10.xlsx in the same folder as app.py.")
    st.stop()

df = coerce_dates(df)

# Preview
with st.expander("🔎 Data preview & info"):
    st.write("**Columns**:", list(df.columns))
    st.write("**Dtypes**:")
    st.write(df.dtypes.astype(str))
    st.dataframe(df.head(20), use_container_width=True)

# Date filter
st.subheader("Filter by Invoice Date")
invoice_dates = df['Invoice date'].dropna()
min_inv = invoice_dates.min().date() if not invoice_dates.empty else date.today()
max_inv = invoice_dates.max().date() if not invoice_dates.empty else date.today()

col_a, col_b = st.columns(2)
with col_a:
    start_date = st.date_input("Start date", value=min_inv, min_value=min_inv, max_value=max_inv)
with col_b:
    end_date = st.date_input("End date", value=max_inv, min_value=min_inv, max_value=max_inv)

if start_date > end_date:
    st.error("Start date cannot be after End date.")
    st.stop()

filtered = filter_by_invoice_date(df, start_date, end_date)

# Summary
st.subheader("Summary")
m1, m2, m3, m4 = st.columns(4)
with m1:
    st.metric("Rows", len(filtered))
with m2:
    st.metric("Total Invoice Value", f"{filtered['Invoice value'].fillna(0).sum():,.2f}")
with m3:
    st.metric("Total Amount Paid", f"{filtered['Amount Paid'].fillna(0).sum():,.2f}")
with m4:
    paid_ct = (filtered['Payment status'].astype(str).str.lower() == 'paid').sum()
    unpaid_ct = (filtered['Payment status'].astype(str).str.lower() != 'paid').sum()
    st.metric("Paid / Unpaid", f"{paid_ct} / {unpaid_ct}")

# Optional filters
st.subheader("Optional Filters")
col_f1, col_f2, col_f3 = st.columns(3)
with col_f1:
    bank_sel = st.multiselect("Bank Name", sorted(filtered['Bank Name'].dropna().unique()))
with col_f2:
    pmode_sel = st.multiselect("Payment mode", sorted(filtered['Payment mode'].dropna().unique()))
with col_f3:
    pstatus_sel = st.multiselect("Payment status", sorted(filtered['Payment status'].dropna().unique()))

f2 = filtered.copy()
if bank_sel:
    f2 = f2[f2['Bank Name'].isin(bank_sel)]
if pmode_sel:
    f2 = f2[f2['Payment mode'].isin(pmode_sel)]
if pstatus_sel:
    f2 = f2[f2['Payment status'].isin(pstatus_sel)]

# Results
st.subheader("Filtered Results")
st.dataframe(f2, use_container_width=True)

# Download buttons
dl_col1, dl_col2 = st.columns(2)
with dl_col1:
    st.download_button("⬇️ Download Excel", data=to_excel_bytes(f2),
                       file_name="filtered_output.xlsx",
                       mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
with dl_col2:
    st.download_button("⬇️ Download CSV", data=f2.to_csv(index=False).encode("utf-8"),
                       file_name="filtered_output.csv", mime="text/csv")

# Notes
st.markdown("""
**Notes**
- Place `Book10.xlsx` in the same folder as `app.py`.
- Dates are converted using `pd.to_datetime(errors='coerce')`.
- Blank or invalid dates become NaT and are excluded from filtering.
""")
