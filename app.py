
# app.py
import streamlit as st
import pandas as pd
from datetime import date
from pathlib import Path

st.set_page_config(page_title="Payments Totals - Bank Breakdown", layout="wide")

EXPECTED_COLS = [
    'Bank Name', 'Payment mode', 'Due date', 'Payment Date', 'Vendor Name',
    'Invoice number', 'Invoice date', 'Invoice value', 'TDS',
    'Amount Paid', 'UTR no.', 'Payment status'
]

# ---------------- Helper Functions ----------------

def read_excel_fix_headers(source) -> pd.DataFrame:
    """Read Excel (path or file-like), drop embedded header row, set EXPECTED_COLS."""
    df_raw = pd.read_excel(source, engine="openpyxl", header=None)
    # Your file has the header repeated as the first row
    df = df_raw.iloc[1:].reset_index(drop=True)
    df.columns = EXPECTED_COLS
    return df

def coerce_dates(df: pd.DataFrame) -> pd.DataFrame:
    """Convert date columns to datetime64[ns] and strip tz if any."""
    for c in ['Due date', 'Payment Date', 'Invoice date']:
        df[c] = pd.to_datetime(df[c], errors='coerce')  # default dayfirst=False
        if pd.api.types.is_datetime64tz_dtype(df[c]):
            df[c] = df[c].dt.tz_localize(None)
    return df

def coerce_numeric(df: pd.DataFrame) -> pd.DataFrame:
    """Numeric columns -> float, invalid -> NaN."""
    for c in ['Invoice value', 'TDS', 'Amount Paid']:
        df[c] = pd.to_numeric(df[c], errors='coerce')
    return df

def filter_by_invoice_date(df: pd.DataFrame, start_dt: date, end_dt: date) -> pd.DataFrame:
    """Inclusive range filter on 'Invoice date' using pandas Series comparisons."""
    start_ts = pd.to_datetime(start_dt)
    end_ts   = pd.to_datetime(end_dt) + pd.Timedelta(days=1) - pd.Timedelta(microseconds=1)
    ser = df['Invoice date']  # keep as Series (no .values)
    mask = ser.notna() & (ser >= start_ts) & (ser <= end_ts)
    return df.loc[mask].copy()

def to_excel_bytes(df_out: pd.DataFrame) -> bytes:
    """Return Excel bytes for download."""
    with pd.ExcelWriter("filtered_output.xlsx", engine="openpyxl") as writer:
        df_out.to_excel(writer, index=False, sheet_name="Filtered")
    with open("filtered_output.xlsx", "rb") as f:
        return f.read()

# ---------------- UI: Source ----------------

st.title("💳 Payments Totals – Bank Breakdown (Minimal)")
st.caption("Upload or point to the Excel file, then filter by date.")

DEFAULT_PATH = Path(__file__).with_name("Book10.xlsx")
with st.expander("📁 Data source"):
    col1, col2 = st.columns([2, 1])
    with col1:
        local_path = st.text_input("Local path:", value=str(DEFAULT_PATH))
    with col2:
        uploaded_file = st.file_uploader("Or upload .xlsx", type=["xlsx"])

# Load priority: uploaded > local path
try:
    if uploaded_file is not None:
        df = read_excel_fix_headers(uploaded_file)
        st.success("✅ Uploaded file loaded.")
        src_used = "uploaded_file"
    else:
        p = Path(local_path)
        if not p.exists():
            st.error("❌ File not found. Upload the file or fix the local path.")
            st.stop()
        df = read_excel_fix_headers(p)
        st.success(f"✅ Loaded local file: {p}")
        src_used = str(p)
except Exception as e:
    st.error(f"Failed to read Excel: {e}")
    st.stop()

# Normalize types
df = coerce_dates(df)
df = coerce_numeric(df)

# Preview
with st.expander("🔎 Data preview & info"):
    st.write("**Source:**", src_used)
    st.write("**Shape:**", df.shape)
    st.write("**Columns:**", list(df.columns))
    st.write("**Dtypes:**")
    st.write(df.dtypes.astype(str))
    st.dataframe(df.head(20), use_container_width=True)

# ---------------- Filters ----------------

st.subheader("Filter by Invoice Date")
invoice_dates = df['Invoice date'].dropna()
min_inv = invoice_dates.min().date() if not invoice_dates.empty else date.today()
max_inv = invoice_dates.max().date() if not invoice_dates.empty else date.today()

c1, c2 = st.columns(2)
with c1:
    start_date = st.date_input("Start date", value=min_inv, min_value=min_inv, max_value=max_inv)
with c2:
    end_date = st.date_input("End date", value=max_inv, min_value=min_inv, max_value=max_inv)

if start_date > end_date:
    st.error("Start date cannot be after End date.")
    st.stop()

filtered = filter_by_invoice_date(df, start_date, end_date)

# ---------------- Summary (Amount Paid & Amount to be Paid) ----------------

# Amount Paid for selected date range
amount_paid = filtered['Amount Paid'].fillna(0).sum()

# Outstanding per row = max(Invoice value - Amount Paid, 0) to avoid negatives
outstanding_series = (filtered['Invoice value'].fillna(0) - filtered['Amount Paid'].fillna(0)).clip(lower=0)
amount_to_be_paid = outstanding_series.sum()

st.subheader("Summary (Selected Date Range)")
m1, m2, m3, m4, m5 = st.columns(5)
with m1:
    st.metric("Rows", len(filtered))
with m2:
    st.metric("Total Invoice Value", f"{filtered['Invoice value'].fillna(0).sum():,.2f}")
with m3:
    st.metric("Amount Paid", f"{amount_paid:,.2f}")
with m4:
    st.metric("Amount to be Paid", f"{amount_to_be_paid:,.2f}")
with m5:
    paid_ct = (filtered['Payment status'].astype(str).str.lower() == 'paid').sum()
    unpaid_ct = (filtered['Payment status'].astype(str).str.lower() != 'paid').sum()
    st.metric("Paid / Unpaid", f"{paid_ct} / {unpaid_ct}")

# ---------------- Optional Filters ----------------

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

# Recompute Amount Paid and Amount to be Paid after optional filters
amount_paid_opt = f2_df['Amount Paid'].fillna(0).sum()
amount_to_be_paid_opt = (f2_df['Invoice value'].fillna(0) - f2_df['Amount Paid'].fillna(0)).clip(lower=0).sum()

st.subheader("Filtered Results (after optional filters)")
o1, o2 = st.columns(2)
with o1:
    st.metric("Amount Paid (after optional filters)", f"{amount_paid_opt:,.2f}")
with o2:
    st.metric("Amount to be Paid (after optional filters)", f"{amount_to_be_paid_opt:,.2f}")

st.dataframe(f2_df, use_container_width=True)

# ---------------- Downloads ----------------

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

st.markdown(r"""
**Notes**
- *Amount Paid* is the sum of the **Amount Paid** column for the selected date range.
- *Amount to be Paid* is calculated as **(Invoice value - Amount Paid)** per row, clipped at zero to avoid negatives, then summed.
- If results differ from local VS Code, confirm the **Source** shown in the preview and ensure the same file is being used.
""")
