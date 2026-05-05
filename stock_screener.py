import pandas as pd
import time
from datetime import datetime
from tvDatafeed import TvDatafeed, Interval
from supabase import create_client

# ---------------- CONFIG ----------------
USERNAME = 'harshmodi1214'
PASSWORD = 'Harsh@Sai@1412'
NIFTY_FILE = 'ind_nifty500list.csv'
N_BARS = 20

SUPABASE_URL = "https://subbrosiecwxtbaxpuzd.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InN1YmJyb3NpZWN3eHRiYXhwdXpkIiwicm9sZSI6ImFub24iLCJpYXQiOjE3Nzc4ODYzNjAsImV4cCI6MjA5MzQ2MjM2MH0.YIpghl4Yzu_gch5JHDlOk9cwG2LvpW8giKmP0TY6YZk"

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)


# ---------------- DB ----------------
def replace_today_data(records, today):
    supabase.table("trade_patterns").delete().eq("date", today).execute()
    supabase.table("trade_patterns").insert(records).execute()


# ---------------- ATR ----------------
def calculate_atr(df, period=14):
    df["prev_close"] = df["close"].shift(1)

    tr = pd.concat([
        df["high"] - df["low"],
        abs(df["high"] - df["prev_close"]),
        abs(df["low"] - df["prev_close"])
    ], axis=1).max(axis=1)

    df["atr"] = tr.rolling(period).mean()
    return df


# ---------------- FETCH ----------------
def fetch_data():
    tv = TvDatafeed(USERNAME, PASSWORD)

    symbols = pd.read_csv(NIFTY_FILE)['Symbol'].tolist()
    data = {}

    for s in symbols:
        try:
            df = tv.get_hist(s, "NSE", Interval.in_daily, n_bars=N_BARS)
            if df is not None and not df.empty:
                data[s] = df
        except Exception as e:
            print(f"{s} failed: {e}")

        time.sleep(0.3)

    combined = pd.concat(data.values(), keys=data.keys())
    combined.to_csv("temp.csv")


# ---------------- PREPROCESS ----------------
def preprocess():
    df = pd.read_csv("temp.csv")
    df["datetime"] = pd.to_datetime(df["datetime"])
    df["Name"] = df["Unnamed: 0"]
    return df.sort_values(["Name", "datetime"])


# ---------------- DETECT ----------------
def detect(df):
    results = []

    for name, g in df.groupby("Name"):
        g = g.reset_index(drop=True)

        if len(g) < 15:
            continue

        g = calculate_atr(g)

        curr = g.iloc[-1]
        prev = g.iloc[-2]
        prev_n = g.iloc[-8:-1]

        atr = curr["atr"]
        if pd.isna(atr):
            continue

        entry = curr["close"]

        # DOJI
        body = abs(curr['close'] - curr['open'])
        rng = curr['high'] - curr['low']

        if rng != 0 and (body / rng) < 0.25:
            if curr['low'] < prev_n['low'].min():
                results.append({
                    "pattern": "Doji",
                    "stock": name,
                    "price": entry,
                    "tp": entry + 1.5 * atr,
                    "sl": curr["low"],
                    "status": None
                })

        # ENGULFING
        if prev['close'] < prev['open'] and curr['close'] > curr['open']:
            if curr['open'] < prev['low'] and curr['close'] > prev['high']:
                results.append({
                    "pattern": "Bullish_Engulfing",
                    "stock": name,
                    "price": entry,
                    "tp": entry + 1.5 * atr,
                    "sl": prev["low"],
                    "status": None
                })

    return results


# ---------------- UPDATE STATUS ----------------
def update_status():
    today = datetime.now().strftime("%Y-%m-%d")

    res = supabase.table("trade_patterns") \
        .select("*") \
        .is_("status", None) \
        .lt("date", today) \
        .execute()

    if not res.data:
        return

    tv = TvDatafeed(USERNAME, PASSWORD)

    for row in res.data:
        try:
            df = tv.get_hist(row["stock"], "NSE", Interval.in_daily, n_bars=2)
            if df is None or df.empty:
                continue

            latest = df.iloc[-1]

            if latest["high"] >= row["tp"]:
                status = "TP Hit"
            elif latest["low"] <= row["sl"]:
                status = "SL Hit"
            else:
                continue

            supabase.table("trade_patterns") \
                .update({"status": status}) \
                .eq("id", row["id"]) \
                .execute()

        except:
            pass


# ---------------- SAVE ----------------
def save(results):
    today = datetime.now().strftime("%Y-%m-%d")

    if not results:
        results = [{
            "pattern": "No_Signal",
            "stock": "NONE",
            "price": None,
            "tp": None,
            "sl": None,
            "status": "No Data"
        }]

    records = [{"date": today, **r} for r in results]
    replace_today_data(records, today)


# ---------------- MAIN ----------------
def run_pipeline():
    print("Running pipeline...")
    update_status()
    fetch_data()
    df = preprocess()
    results = detect(df)
    save(results)
    print("Done")
