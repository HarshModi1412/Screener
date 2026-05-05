import streamlit as st
import pandas as pd
from datetime import datetime
from supabase import create_client
from stock_screener import run_pipeline

# ---------------- CONFIG ----------------
st.set_page_config(page_title="Stock Platform", layout="wide")

SUPABASE_URL = "https://subbrosiecwxtbaxpuzd.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InN1YmJyb3NpZWN3eHRiYXhwdXpkIiwicm9sZSI6ImFub24iLCJpYXQiOjE3Nzc4ODYzNjAsImV4cCI6MjA5MzQ2MjM2MH0.YIpghl4Yzu_gch5JHDlOk9cwG2LvpW8giKmP0TY6YZk"

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)


# ---------------- HELPERS ----------------
def get_latest_date():
    res = supabase.table("trade_patterns") \
        .select("date") \
        .order("date", desc=True) \
        .limit(1) \
        .execute()

    if not res.data:
        return None

    return pd.to_datetime(res.data[0]["date"])


def load_data():
    res = supabase.table("trade_patterns") \
        .select("*") \
        .order("date", desc=True) \
        .execute()

    df = pd.DataFrame(res.data)

    if not df.empty:
        df["date"] = pd.to_datetime(df["date"])

    return df


def auto_run():
    today = pd.to_datetime(datetime.now().strftime("%Y-%m-%d"))
    latest = get_latest_date()

    if latest is None or latest != today:
        st.warning("⚡ Running pipeline...")
        with st.spinner("Processing market data..."):
            run_pipeline()
        st.rerun()


# ---------------- UI ----------------
st.title("📈 Market Screener")

auto_run()

df = load_data()

if df.empty:
    st.error("No data available")
    st.stop()

latest_date = df["date"].max().date()
st.success(f"📅 Showing data for: {latest_date}")

if st.button("🔄 Refresh"):
    with st.spinner("Recomputing signals..."):
        run_pipeline()
    st.rerun()


# ---------------- KPI ----------------
patterns = sorted(df["pattern"].unique())
cols = st.columns(len(patterns))

for i, p in enumerate(patterns):
    cols[i].metric(p, len(df[df["pattern"] == p]))


# ---------------- FILTER ----------------
pattern = st.selectbox("Pattern", patterns)
search = st.text_input("Search")

filtered = df[df["pattern"] == pattern]

if search:
    filtered = filtered[filtered["stock"].str.contains(search, case=False)]

stocks = filtered["stock"].tolist()


# ---------------- DISPLAY ----------------
def stock_tile(name):
    return f"""
    <a href="https://www.tradingview.com/chart/?symbol=NSE:{name}" target="_blank">
        <div style="padding:12px;background:#111;color:white;border-radius:8px;text-align:center;margin:4px;">
            {name}
        </div>
    </a>
    """

rows = [stocks[i:i+6] for i in range(0, len(stocks), 6)]

for row in rows:
    cols = st.columns(6)
    for i, s in enumerate(row):
        cols[i].markdown(stock_tile(s), unsafe_allow_html=True)
