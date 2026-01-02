
# app.py
import os
import platform
from pathlib import Path
from datetime import date

import pandas as pd
import streamlit as st

st.set_page_config(page_title="Payments Totals - Bank Breakdown", layout="wide")

# ----------------- Constants -----------------
EXPECTED_COLS = [
    'Bank Name', 'Payment mode', 'Due date', 'Payment Date', 'Vendor Name',
    'Invoice number', 'Invoice date', 'Invoice value', 'TDS',
    'Amount Paid', 'UTR no.', 'Payment status'
]

DEFAULT_PATH = Path(__file__).with_name("Book10.xlsx")


# ----------------- Helpers -----------------
def read_excel_fix_headers(source) -> pd.DataFrame:
    """
    Read Excel from a path or file-like object, drop the embedded header row,
    and set deterministic column names.
    """
    df_raw = pd.read_excel(source, engine="openpyxl", header=None)
    # Your file repeats the header as the first row -> drop it
    df = df_raw.iloc[1:].reset_index(drop=True)
    df.columns = EXPECTED_COLS
    return df


def coerce_dates_with_choice(df: pd.DataFrame, fmt_choice: str) -> pd.DataFrame:
    """
    Convert date columns to datetime64[ns], using a chosen format to ensure identical parsing
    across environments. Strip timezone if present.
    """
    date_cols = ['Due date', 'Payment Date', 'Invoice date']

    if fmt_choice == "Auto (infer formats)":
        for c in date_cols:
            df[c] = pd.to_datetime(df[c], errors='coerce')
    elif fmt_choice == "MM/DD/YYYY":
        for c in date_cols:
            df[c] = pd.to_datetime(df[c], format="%m/%d/%Y", errors='coerce')
    elif fmt_choice == "DD/MM/YYYY":
        for c in date_cols:
            df[c] = pd.to_datetime(df[c], format="%d/%m/%Y", errors='coerce')
    else:
        for c in date_cols:
            df[c] = pd.to_datetime(df[c], errors='coerce')

    for c in date_cols:
        if pd.api.types.is_datetime64tz_dtype(df[c]):
            df[c] = df[c].dt.tz_localize(None)

    return df


def coerce_numeric(df: pd.DataFrame) -> pd.DataFrame:
    """Ensure numeric columns are floats; invalid values become NaN."""
    for c in ['Invoice value', 'TDS', 'Amount Paid']:
        df[c] = pd.to_numeric(df[c], errors='coerce')
    return df


def filter_by_due_date(df: pd.DataFrame, start_dt: date, end_dt: date) -> pd.DataFrame:
    """
    Inclusive date-range filter on 'Due date' using pandas Series comparisons.
    """
    start_ts = pd.to_datetime(start_dt)  # midnight
    end_ts = pd.to_datetime(end_dt) + pd.Timedelta(days=1) - pd.Timedelta(microseconds=1)  # end-of-day inclusive

    ser = df['Due date']  # keep as Series (no .values)
    mask = ser.notna() & (ser >= start_ts) & (ser <= end_ts)
    return df.loc[mask].copy()


def compute_totals_both(filtered: pd.DataFrame) -> dict:
    """
    Compute summary totals on the filtered frame.
    Returns both kinds of outstanding:
      - amount_to_be_paid_all: outstanding across ALL filtered rows
      - amount_to_be_paid_unpaid_only: outstanding only for rows with status != 'Paid'
    """
    inv_val = filtered['Invoice value'].fillna(0)
    amt_paid = filtered['Amount Paid'].fillna(0)

    # Overall outstanding across ALL filtered rows (never negative)
    outstanding_all = (inv_val - amt_paid).clip(lower=0)
    amount_to_be_paid_all = float(outstanding_all.sum())

    # Outstanding only for rows marked Un paid
    unpaid_mask = filtered['Payment status'].astype(str).str.lower() != 'paid'
    outstanding_unpaid_only = (
        filtered.loc[unpaid_mask, 'Invoice value'].fillna(0)
        - filtered.loc[unpaid_mask, 'Amount Paid'].fillna(0)
    ).clip(lower=0)
    amount_to_be_paid_unpaid_only = float(outstanding_unpaid_only.sum())

    return {
        "rows": len(filtered),
        "total_invoice_value": float(inv_val.sum()),
        "amount_paid": float(amt_paid.sum()),
        "amount_to_be_paid_all": amount_to_be_paid_all,
        "amount_to_be_paid_unpaid_only": amount_to_be_paid_unpaid_only,
        "paid_ct": int((filtered['Payment status'].astype(str).str.lower() == 'paid').sum()),
        "unpaid_ct": int(unpaid_mask.sum()),
    }


def to_excel_bytes(df_out: pd.DataFrame) -> bytes:
    """Return Excel bytes for download."""
    with pd.ExcelWriter("filtered_output.xlsx", engine="openpyxl") as writer:
        df_out.to_excel(writer, index=False, sheet_name="Filtered")
    with open("filtered_output.xlsx", "rb") as f:
        return f.read()


# ----------------- UI: Data source -----------------
st.title("💳 Payments Totals – Bank Breakdown (Minimal, Due date)")

with st.expander("📁 Data source"):
    col1, col2 = st.columns([2, 1])
    with col1:
        local_path = st.text_input("Local Excel path (optional):", value=str(DEFAULT_PATH))
    with col2:
        uploaded_file = st.file_uploader("Or upload .xlsx", type=["xlsx"])

st.subheader("Parsing options")
date_format_choice = st.radio(
    "Choose date format to parse:",
    options=["Auto (infer formats)", "MM/DD/YYYY", "DD/MM/YYYY"],
    index=0,
    horizontal=True
)

# Load priority: uploaded > local path
try:
    if uploaded_file is not None:
        df = read_excel_fix_headers(uploaded_file)
        src_used = "uploaded_file"
        st.success("✅ Uploaded file loaded.")
    else:
        p = Path(local_path)
        if not p.exists():
            st.error("❌ File not found. Upload the file or fix the local path shown above.")
            st.stop()
        df = read_excel_fix_headers(p)
        src_used = str(p)
        st.success(f"✅ Loaded local file: {p}")
except Exception as e:
    st.error(f"Failed to read Excel: {e}")
    st.stop()

# Normalize types
df = coerce_dates_with_choice(df, date_format_choice)
df = coerce_numeric(df)

# ----------------- Diagnostics (optional) -----------------
with st.expander("🔎 Diagnostics (optional)", expanded=False):
    st.write("**Python**:", platform.python_version())
    st.write("**pandas**:", pd.__version__)
    st.write("**CWD**:", os.getcwd())
    st.write("**Source used:**", src_used)
    st.write("**Shape (rows, cols):**", df.shape)
    st.write("**Head (first 20 rows):**")
    st.dataframe(df.head(20), use_container_width=True)

# ----------------- Filters -----------------
st.subheader("Filter by Due Date")

due_dates = df['Due date'].dropna()
min_due = due_dates.min().date() if not due_dates.empty else date.today()
max_due = due_dates.max().date() if not due_dates.empty else date.today()

c1, c2 = st.columns(2)
with c1:
    start_date = st.date_input("Start date", value=min_due, min_value=min_due, max_value=max_due)
with c2:
    end_date = st.date_input("End date", value=max_due, min_value=min_due, max_value=max_due)

if start_date > end_date:
    st.error("Start date cannot be after End date.")
    st.stop()

filtered = filter_by_due_date(df, start_date, end_date)

# ----------------- Choice: which outstanding to show -----------------
choice = st.radio(
    "Amount to be Paid (Outstanding) should calculate for:",
    ["All filtered rows", "Only rows with status 'Un paid'"],
    index=0,
    horizontal=True
)

# ----------------- Summary -----------------
totals = compute_totals_both(filtered)

amount_to_show = (
    totals["amount_to_be_paid_all"]
    if choice == "All filtered rows"
    else totals["amount_to_be_paid_unpaid_only"]
)

st.subheader("Summary (Selected Due Date Range)")
m1, m2, m3, m4, m5 = st.columns(5)
with m1:
    st.metric("Rows", totals["rows"])
with m2:
    st.metric("Total Invoice Value", f"{totals['total_invoice_value']:,.2f}")
with m3:
    st.metric("Amount Paid", f"{totals['amount_paid']:,.2f}")
with m4:
    st.metric("Amount to be Paid (Outstanding)", f"{amount_to_show:,.2f}")
with m5:
    st.metric("Paid / Unpaid", f"{totals['paid_ct']} / {totals['unpaid_ct']}")

# ----------------- Optional Filters -----------------
st.subheader("Optional Filters")
f1, f2, f3 = st.columns(3)
with f1:
    bank_sel = st.multiselect("Bank Name", sorted(filtered['Bank Name'].dropna().unique()))
with f2:
    pmode_sel = st.multiselect("Payment mode", sorted(filtered['Payment mode'].dropna().unique()))
with f3:
    pstatus_sel = st.multiselect("Payment status", sorted(filtered['Payment status'].dropna().unique()))

f2_df = filtered.copy()
if bank_sel:
    f2_df = f2_df[f2_df['Bank Name'].isin(bank_sel)]
if pmode_sel:
    f2_df = f2_df[f2_df['Payment mode'].isin(pmode_sel)]
if pstatus_sel:
    f2_df = f2_df[f2_df['Payment status'].isin(pstatus_sel)]

totals_opt = compute_totals_both(f2_df)
amount_to_show_opt = (
    totals_opt["amount_to_be_paid_all"]
    if choice == "All filtered rows"
    else totals_opt["amount_to_be_paid_unpaid_only"]
)

st.subheader("Filtered Results (after optional filters)")
o1, o2 = st.columns(2)
with o1:
    st.metric("Amount Paid (after optional filters)", f"{totals_opt['amount_paid']:,.2f}")
with o2:
    st.metric("Amount to be Paid (after optional filters)", f"{amount_to_show_opt:,.2f}")

st.dataframe(f2_df, use_container_width=True)

# ----------------- Downloads -----------------
c_dl1, c_dl2 = st.columns(2)
with c_dl1:
    st.download_button(
        "⬇️ Download Excel",
        data=to_excel_bytes(f2_df),
        file_name="filtered_output.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
with c_dl2:
    st.download_button(
        "⬇️ Download CSV",
        data=f2_df.to_csv(index=False).encode("utf-8"),
        file_name="filtered_output.csv",
        mime="text/csv",
    )

# ----------------- Notes -----------------
st.markdown(r"""
**Notes**
- Place `Book10.xlsx` next to `app.py` or upload it via the top uploader.
- Select the correct **date format** (Auto/MM/DD/YYYY/DD/MM/YYYY) to ensure identical parsing between VS Code and Streamlit.
- Filtering and summaries are based on **Due date** (inclusive end-of-day).
- *Amount to be Paid (Outstanding)* can be shown for **all filtered rows** or **only rows marked 'Un paid'** — use the radio choice above.
- Comparisons use pandas **Series vs Timestamp** (no NumPy arrays), avoiding the original `TypeError`.
""")
