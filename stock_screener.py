import pandas as pd
import time
from datetime import datetime
from tvDatafeed import TvDatafeed, Interval
from supabase import create_client

# ---------------- CONFIG ----------------
USERNAME = 'harshmodi1214'
PASSWORD = 'Harsh@Sai@1412'
NIFTY_FILE = 'ind_nifty500list.csv'
N_BARS = 20  # for ATR

SUPABASE_URL = "https://subbrosiecwxtbaxpuzd.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InN1YmJyb3NpZWN3eHRiYXhwdXpkIiwicm9sZSI6ImFub24iLCJpYXQiOjE3Nzc4ODYzNjAsImV4cCI6MjA5MzQ2MjM2MH0.YIpghl4Yzu_gch5JHDlOk9cwG2LvpW8giKmP0TY6YZk"

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)


# ---------------- DB HELPERS ----------------
def replace_today_data(records, today):
    supabase.table("trade_patterns").delete().eq("date", today).execute()
    supabase.table("trade_patterns").insert(records).execute()


# ---------------- ATR ----------------
def calculate_atr(df, period=14):
    df["prev_close"] = df["close"].shift(1)

    tr1 = df["high"] - df["low"]
    tr2 = abs(df["high"] - df["prev_close"])
    tr3 = abs(df["low"] - df["prev_close"])

    df["tr"] = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    df["atr"] = df["tr"].rolling(period).mean()

    return df


# ---------------- FETCH ----------------
def fetch_data():
    tv = TvDatafeed(USERNAME, PASSWORD)

    symbols = pd.read_csv(NIFTY_FILE)['Symbol'].tolist()
    data_dict = {}

    for symbol in symbols:
        try:
            df = tv.get_hist(
                symbol=symbol,
                exchange='NSE',
                interval=Interval.in_daily,
                n_bars=N_BARS
            )
            if df is not None and not df.empty:
                data_dict[symbol] = df

        except Exception as e:
            print(f"Failed {symbol}: {e}")

        time.sleep(0.3)

    combined = pd.concat(data_dict.values(), keys=data_dict.keys())
    combined.to_csv("temp_data.csv")
    return combined


# ---------------- PREPROCESS ----------------
def preprocess():
    df = pd.read_csv("temp_data.csv")
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

        # ---------------- DOJI ----------------
        body = abs(curr['close'] - curr['open'])
        rng = curr['high'] - curr['low']

        is_doji = (body / rng) < 0.25 if rng != 0 else False
        lowest = curr['low'] < prev_n['low'].min()
        red = (prev_n['close'] < prev_n['open']).sum() >= 1

        if is_doji and lowest and red:
            results.append({
                "pattern": "Doji",
                "stock": name,
                "price": float(entry),
                "tp": float(entry + 1.5 * atr),
                "sl": float(curr["low"]),
                "status": None
            })

        # ---------------- ENGULFING ----------------
        if (
            prev['close'] < prev['open'] and
            curr['close'] > curr['open'] and
            curr['open'] < prev['low'] and
            curr['close'] > prev['high']
        ):
            results.append({
                "pattern": "Bullish_Engulfing",
                "stock": name,
                "price": float(entry),
                "tp": float(entry + 1.5 * atr),
                "sl": float(prev["low"]),
                "status": None
            })

        # ---------------- PIERCING ----------------
        prev_mid = (prev['open'] + prev['close']) / 2

        if (
            prev['close'] < prev['open'] and
            curr['close'] > curr['open'] and
            curr['open'] < prev['low'] and
            curr['close'] > prev_mid
        ):
            results.append({
                "pattern": "Bullish_Piercing",
                "stock": name,
                "price": float(entry),
                "tp": float(entry + 1.5 * atr),
                "sl": float(prev["low"]),
                "status": None
            })

        # ---------------- MARUBOZU ----------------
        body = abs(curr['close'] - curr['open'])
        upper = curr['high'] - max(curr['close'], curr['open'])
        lower = min(curr['close'], curr['open']) - curr['low']

        if body != 0 and (upper/body) < 0.1 and (lower/body) < 0.1:
            results.append({
                "pattern": "Bullish_Marubozu",
                "stock": name,
                "price": float(entry),
                "tp": float(entry + 1.5 * atr),
                "sl": float(curr["low"]),
                "status": None
            })

    return results

# ---------------- UPDATE STATUS ----------------
def update_trade_status():
    print("Updating trade status...")

    today = datetime.now().strftime("%Y-%m-%d")

    res = supabase.table("trade_patterns") \
        .select("*") \
        .is_("status", None) \
        .lt("date", today) \
        .execute()

    if not res.data:
        print("No open trades")
        return

    tv = TvDatafeed(USERNAME, PASSWORD)

    for row in res.data:
        try:
            df = tv.get_hist(
                symbol=row["stock"],
                exchange="NSE",
                interval=Interval.in_daily,
                n_bars=3
            )

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

            print(f"{row['stock']} → {status}")

        except Exception as e:
            print(f"Error {row['stock']}: {e}")


# ---------------- SAVE ----------------
def save(results):
    today = datetime.now().strftime("%Y-%m-%d")

    records = []
    for r in results:
        records.append({
            "date": today,
            "pattern": r["pattern"],
            "stock": r["stock"],
            "price": r["price"],
            "tp": r["tp"],
            "sl": r["sl"],
            "status": None
        })

    if not records:
        records.append({
            "date": today,
            "pattern": "No_Signal",
            "stock": "NONE",
            "price": None,
            "tp": None,
            "sl": None,
            "status": "No Data"
        })

    replace_today_data(records, today)


# ---------------- MAIN PIPELINE ----------------
def run_pipeline():
    print("Running pipeline...")

    update_trade_status()
    fetch_data()
    df = preprocess()
    results = detect(df)
    save(results)

    print("Pipeline completed")


if __name__ == "__main__":
    run_pipeline()