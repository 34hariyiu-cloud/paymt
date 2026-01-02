
# app.py
import streamlit as st
import pandas as pd
from datetime import date
from pathlib import Path

st.set_page_config(page_title="Payments Totals - Bank Breakdown", layout="wide")

# --------------- Constants ---------------
EXPECTED_COLS = [
    'Bank Name', 'Payment mode', 'Due date', 'Payment Date', 'Vendor Name',
    'Invoice number', 'Invoice date', 'Invoice value', 'TDS',
    'Amount Paid', 'UTR no.', 'Payment status'
]

# Default local path: a file named Book10.xlsx next to app.py
DEFAULT_LOCAL_PATH = Path(__file__).with_name("Book10.xlsx")

# --------------- Helper functions ---------------

def fix_headers(df_raw: pd.DataFrame) -> pd.DataFrame:
    """
    Normalize headers to EXPECTED_COLS.
    Your Excel has the header row embedded as the first data row. We drop it and set EXPECTED_COLS.
    """
    first_row = df_raw.iloc[0].astype(str).tolist()
    if 'Bank Name' in first_row:
        df = df_raw.iloc[1:].reset_index(drop=True)
        df.columns = EXPECTED_COLS
    else:
        df = df_raw.copy()
        df.columns = EXPECTED_COLS
    return df


def read_excel_any(source) -> pd.DataFrame:
    """
    Read Excel from a file path (str/Path) or a file-like object (Streamlit uploader).
    Always read with header=None, then fix headers with fix_headers().
    """
    df_raw = pd.read_excel(source, engine="openpyxl", header=None)
    df = fix_headers(df_raw)
    return df


def coerce_dates(df: pd.DataFrame) -> pd.DataFrame:
    """
    Convert date-like columns to datetime64[ns] with safe coercion.
    Any invalid/missing dates become NaT.
    """
    for c in ['Due date', 'Payment Date', 'Invoice date']:
        if c in df.columns:
            df[c] = pd.to_datetime(df[c], errors='coerce')  # dayfirst=False by default
            if pd.api.types.is_datetime64tz_dtype(df[c]):
                df[c] = df[c].dt.tz_localize(None)
    return df


def coerce_numeric(df: pd.DataFrame) -> pd.DataFrame:
    """Ensure numeric columns are numeric (float). Invalid entries become NaN."""
    for c in ['Invoice value', 'TDS', 'Amount Paid']:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors='coerce')
    return df


def filter_by_date_range(df: pd.DataFrame, start_dt: date, end_dt: date, date_col: str) -> pd.DataFrame:
    """
    Inclusive date-range filter on the chosen date column.
    Keeps comparisons in pandas Series to avoid ndarray-vs-Timestamp TypeError.
    """
    if date_col not in df.columns:
        st.warning(f"Column '{date_col}' not found. Available: {list(df.columns)}")
        return df.copy()

    ser = df[date_col]
    start_ts = pd.to_datetime(start_dt)  # midnight
    end_ts   = pd.to_datetime(end_dt)
    end_ts = end_ts + pd.Timedelta(days=1) - pd.Timedelta(microseconds=1)  # inclusive end-of-day
    mask = ser.notna() & (ser >= start_ts) & (ser <= end_ts)
    return df.loc[mask].copy()


def add_optional_filters(df: pd.DataFrame, bank_sel=None, pmode_sel=None, vendor_sel=None, pstatus_sel=None) -> pd.DataFrame:
    """Apply optional filters based on multiselect inputs."""
    out = df.copy()
    if bank_sel:
        out = out[out['Bank Name'].isin(bank_sel)]
    if pmode_sel:
        out = out[out['Payment mode'].isin(pmode_sel)]
    if vendor_sel:
        out = out[out['Vendor Name'].isin(vendor_sel)]
    if pstatus_sel:
        out = out[out['Payment status'].isin(pstatus_sel)]
    return out


def to_excel_bytes(df_out: pd.DataFrame) -> bytes:
    """Return Excel bytes for download."""
    with pd.ExcelWriter("filtered_output.xlsx", engine="openpyxl") as writer:
        df_out.to_excel(writer, index=False, sheet_name="Filtered")
    with open("filtered_output.xlsx", "rb") as f:
        return f.read()


# --------------- UI: Data loading ---------------

st.title("💳 Payments Totals – Bank Breakdown")

st.caption("Load from local file if present, or upload an Excel file with the same columns.")

df = None

with st.expander("📁 Data source"):
    col_src1, col_src2 = st.columns([2, 1])
    with col_src1:
        # Text input defaults to the Book10.xlsx next to app.py
        custom_path = st.text_input(
            "Local Excel file path (optional)",
            value=str(DEFAULT_LOCAL_PATH),
            placeholder=r"C:\Users\Sivaprakash\Downloads\payments_totals_streamlit_bank_breakdown\Book10.xlsx"
        )
    with col_src2:
        uploaded_file = st.file_uploader("Or upload Excel (.xlsx)", type=["xlsx"])

# Priority: uploaded file > custom path
try:
    if uploaded_file is not None:
        df = read_excel_any(uploaded_file)
        st.success("✅ Uploaded file loaded successfully.")
    else:
        p = Path(custom_path)
        if p.exists():
            df = read_excel_any(p)
            st.success(f"✅ Loaded local file: {p}")
        else:
            st.error("❌ File not found. Please upload an Excel file or provide a valid local path.")
            st.stop()
except Exception as e:
    st.error(f"Failed to read Excel: {e}")
    st.stop()

# Coerce dates & numeric columns
df = coerce_dates(df)
df = coerce_numeric(df)

# Preview
with st.expander("🔎 Data preview & info", expanded=False):
    st.write("**Columns**:", list(df.columns))
    st.write("**Dtypes**:")
    st.write(df.dtypes.astype(str))
    st.write("**Sample rows**:")
    st.dataframe(df.head(20), use_container_width=True)

# --------------- UI: Filters ---------------

st.subheader("Filter controls")

date_col_choice = st.selectbox(
    "Filter by date column",
    options=['Invoice date', 'Payment Date', 'Due date'],
    index=0
)

date_series = df[date_col_choice].dropna()
if not date_series.empty:
    min_dt = date_series.min().date()
    max_dt = date_series.max().date()
else:
    min_dt = date.today()
    max_dt = date.today()

col_date1, col_date2 = st.columns(2)
with col_date1:
    start_date = st.date_input("Start date", value=min_dt, min_value=min_dt, max_value=max_dt)
with col_date2:
    end_date = st.date_input("End date", value=max_dt, min_value=min_dt, max_value=max_dt)

if start_date > end_date:
    st.error("Start date cannot be after End date. Please adjust.")
    st.stop()

col_f1, col_f2, col_f3, col_f4 = st.columns(4)
with col_f1:
    bank_sel = st.multiselect("Bank Name", sorted([x for x in df['Bank Name'].dropna().unique()]))
with col_f2:
    pmode_sel = st.multiselect("Payment mode", sorted([x for x in df['Payment mode'].dropna().unique()]))
with col_f3:
    vendor_sel = st.multiselect("Vendor Name", sorted([x for x in df['Vendor Name'].dropna().unique()]))
with col_f4:
    pstatus_sel = st.multiselect("Payment status", sorted([x for x in df['Payment status'].dropna().unique()]))

filtered = filter_by_date_range(df, start_date, end_date, date_col_choice)
filtered = add_optional_filters(filtered, bank_sel, pmode_sel, vendor_sel, pstatus_sel)

# --------------- Summaries ---------------

st.subheader("Summary (within selected filters)")
m1, m2, m3, m4 = st.columns(4)
with m1:
    st.metric("Rows", value=len(filtered))
with m2:
    st.metric("Total Invoice Value", value=f"{filtered['Invoice value'].fillna(0).sum():,.2f}")
with m3:
    st.metric("Total Amount Paid", value=f"{filtered['Amount Paid'].fillna(0).sum():,.2f}")
with m4:
    paid_ct = int((filtered['Payment status'].astype(str).str.lower() == 'paid').sum())
    unpaid_ct = int((filtered['Payment status'].astype(str).str.lower() != 'paid').sum())
    st.metric("Paid / Unpaid", value=f"{paid_ct} / {unpaid_ct}")

st.subheader("Pivot summaries")
c_p1, c_p2 = st.columns(2)

with c_p1:
    st.caption("Amount Paid by Bank")
    by_bank = (
        filtered.groupby('Bank Name', dropna=True)['Amount Paid']
        .sum()
        .reset_index()
        .sort_values('Amount Paid', ascending=False)
    )
    st.dataframe(by_bank, use_container_width=True)
    if not by_bank.empty:
        st.bar_chart(by_bank.set_index('Bank Name'))

with c_p2:
    st.caption("Invoice Value by Payment status")
    by_status = (
        filtered.groupby('Payment status', dropna=True)['Invoice value']
        .sum()
        .reset_index()
        .sort_values('Invoice value', ascending=False)
    )
    st.dataframe(by_status, use_container_width=True)
    if not by_status.empty:
        st.bar_chart(by_status.set_index('Payment status'))

# --------------- Results table & downloads ---------------

st.subheader("Filtered Results")
st.dataframe(filtered, use_container_width=True)

dl_col1, dl_col2 = st.columns(2)
with dl_col1:
    st.download_button(
        label="⬇️ Download filtered (Excel)",
        data=to_excel_bytes(filtered),
        file_name="filtered_output.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        use_container_width=True
    )
with dl_col2:
    st.download_button(
        label="⬇️ Download filtered (CSV)",
        data=filtered.to_csv(index=False).encode("utf-8"),
        file_name="filtered_output.csv",
        mime="text/csv",
        use_container_width=True
    )

# --------------- Notes ---------------
st.markdown(r"""
**Notes & Tips**
- Date columns (**Invoice date**, **Payment Date**, **Due date**) are converted to `datetime64[ns]` via `pd.to_datetime(..., errors='coerce')`.
- Invalid or blank dates become **NaT** and are excluded by the date range filter (`.notna()`).
- The date mask compares **pandas Series** to **pandas Timestamps**:
  ```python
  mask = ser.notna() & (ser >= start_ts) & (ser <= end_ts)
