
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

# ---------- Helpers ----------
def read_excel_fix_headers(source) -> pd.DataFrame:
    """
    Read Excel from path or file-like object, drop the embedded header row,
    set EXPECTED_COLS deterministically.
    """
    df_raw = pd.read_excel(source, engine="openpyxl", header=None)
    # Your file has a duplicated header in first row -> drop it
    df = df_raw.iloc[1:].reset_index(drop=True)
    df.columns = EXPECTED_COLS
    return df

def coerce_dates(df: pd.DataFrame) -> pd.DataFrame:
    """Convert date columns to datetime64[ns] and strip tz if present."""
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

def filter_by_invoice_date(df: pd.DataFrame, start_dt: date, end_dt: date, date_col: str = 'Invoice date') -> pd.DataFrame:
    """Inclusive range filter using pandas Series comparisons."""
    # Normalize bounds
    start_ts = pd.to_datetime(start_dt)  # midnight
    end_ts   = pd.to_datetime(end_dt) + pd.Timedelta(days=1) - pd.Timedelta(microseconds=1)

    # Ensure column exists and is datetime (already coerced above)
    if date_col not in df.columns:
        st.warning(f"Column '{date_col}' not in DataFrame.")
        return df.copy()

    ser = df[date_col]  # KEEP AS SERIES
    mask = ser.notna() & (ser >= start_ts) & (ser <= end_ts)
    return df.loc[mask].copy()

def to_excel_bytes(df_out: pd.DataFrame) -> bytes:
    """Return Excel bytes for download."""
    with pd.ExcelWriter("filtered_output.xlsx", engine="openpyxl") as writer:
        df_out.to_excel(writer, index=False, sheet_name="Filtered")
    with open("filtered_output.xlsx", "rb") as f:
        return f.read()

# ---------- UI: source ----------
st.title("💳 Payments Totals – Bank Breakdown (Minimal)")
st.caption("Upload or point to the Excel file, then filter and download results.")

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
        st.success("✅ Uploaded file loaded")
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
    st.write("**Source**:", src_used)
    st.write("**Shape**:", df.shape)
    st.write("**Columns**:", list(df.columns))
    st.write("**Dtypes**:")
    st.write(df.dtypes.astype(str))
    st.dataframe(df.head(20), use_container_width=True)

# ---------- Filters ----------
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

st.subheader("Filtered Results")
st.dataframe(f2_df, use_container_width=True)

# Downloads
c_dl1, c_dl2 = st.columns(2)
with c_dl1:
    st.download_button("⬇️ Download Excel", data=to_excel_bytes(f2_df),
                       file_name="filtered_output.xlsx",
                       mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
with c_dl2:
    st.download_button("⬇️ Download CSV", data=f2_df.to_csv(index=False).encode("utf-8"),
                       file_name="filtered_output.csv", mime="text/csv")

st.markdown(r"""
**Notes**
- Ensure you're loading the **same Excel file** you used in VS Code (check "Source" above).
- Date comparisons are performed on pandas **Series** vs **Timestamp** only (no NumPy arrays).
- Invalid or blank dates become NaT and are excluded by the date range.
""")
