import streamlit as st
import pandas as pd
import subprocess
from datetime import datetime
from supabase import create_client

from simulator import show_simulator
from manual_simulator import show_manual_simulator

# ---------------- CONFIG ----------------
st.set_page_config(page_title="Stock Platform", layout="wide")

PIPELINE_FILE = "stock_screener.py"

SUPABASE_URL = "https://subbrosiecwxtbaxpuzd.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InN1YmJyb3NpZWN3eHRiYXhwdXpkIiwicm9sZSI6ImFub24iLCJpYXQiOjE3Nzc4ODYzNjAsImV4cCI6MjA5MzQ2MjM2MH0.YIpghl4Yzu_gch5JHDlOk9cwG2LvpW8giKmP0TY6YZk"

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)


# ---------------- HELPERS ----------------
def run_pipeline():
    with st.spinner("⚡ Running pipeline... please wait (~7 min)"):
        subprocess.run(["python", PIPELINE_FILE], check=True)
    st.success("Pipeline completed")
    st.rerun()


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

    if df.empty:
        return df

    df["date"] = pd.to_datetime(df["date"])
    return df


def auto_run():
    today = pd.to_datetime(datetime.now().strftime("%Y-%m-%d"))
    latest = get_latest_date()

    if latest is None or latest != today:
        st.warning("⚡ No latest data. Running pipeline...")
        run_pipeline()
        st.stop()


def stock_tile(name):
    url = f"https://www.tradingview.com/chart/?symbol=NSE:{name}"

    return f"""
    <a href="{url}" target="_blank" style="text-decoration:none;">
        <div style="
            background: linear-gradient(145deg, #0f172a, #020617);
            padding: 14px;
            margin: 6px;
            border-radius: 12px;
            text-align: center;
            font-weight: 600;
            color: #e2e8f0;
            border: 1px solid rgba(255,255,255,0.08);
            box-shadow: 0 4px 12px rgba(0,0,0,0.4);
            transition: all 0.25s ease;
            cursor: pointer;
        "
        onmouseover="this.style.transform='translateY(-4px) scale(1.03)'; this.style.boxShadow='0 10px 25px rgba(0,0,0,0.6)'; this.style.border='1px solid rgba(59,130,246,0.5)';"
        onmouseout="this.style.transform='none'; this.style.boxShadow='0 4px 12px rgba(0,0,0,0.4)'; this.style.border='1px solid rgba(255,255,255,0.08)';"
        >
            <div style="font-size:14px; letter-spacing:0.5px;">
                {name}
            </div>
        </div>
    </a>
    """


# ---------------- SIDEBAR ----------------
st.sidebar.title("📊 Terminal")

page = st.sidebar.radio(
    "Go to",
    ["Screener", "Simulator (Auto)", "Simulator (Manual)"]
)

if page == "Simulator (Auto)":
    show_simulator()
    st.stop()

if page == "Simulator (Manual)":
    show_manual_simulator()
    st.stop()


# ---------------- MAIN ----------------
st.title("📈 Market Screener")

auto_run()

df = load_data()

if df.empty:
    st.error("No data")
    st.stop()

latest_date = df["date"].max().date()
st.success(f"📅 Showing data for: {latest_date}")

if st.button("🔄 Refresh"):
    run_pipeline()

# ---------------- KPIs ----------------
patterns = sorted(df["pattern"].unique())
cols = st.columns(len(patterns))

for i, p in enumerate(patterns):
    with cols[i]:
        st.metric(p, len(df[df["pattern"] == p]))

# ---------------- FILTER ----------------
pattern = st.selectbox("Pattern", patterns)
search = st.text_input("Search")

filtered = df[df["pattern"] == pattern]

if search:
    filtered = filtered[filtered["stock"].str.contains(search, case=False)]

stocks = filtered["stock"].tolist()

# ---------------- DISPLAY ----------------
if not stocks:
    st.info("No signals")
    st.stop()

rows = [stocks[i:i+6] for i in range(0, len(stocks), 6)]

for row in rows:
    cols = st.columns(6)
    for i, s in enumerate(row):
        cols[i].markdown(stock_tile(s), unsafe_allow_html=True)