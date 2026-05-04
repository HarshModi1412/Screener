import streamlit as st
import pandas as pd
import numpy as np
from tvDatafeed import TvDatafeed, Interval
import plotly.graph_objects as go

tv = TvDatafeed('harshmodi1214', 'Harsh@Sai@1412')


# -------- DATA --------
def get_stock_data(symbol, days):
    try:
        df = tv.get_hist(symbol=symbol, exchange='NSE',
                         interval=Interval.in_daily, n_bars=int(days))

        if df is None or df.empty:
            return None

        return df.reset_index()

    except:
        return None


# -------- PREP --------
def prepare_data(df, p):

    df = df.copy().reset_index(drop=True)

    df['HL'] = df['high'] - df['low']
    df['HC'] = abs(df['high'] - df['close'].shift(1))
    df['LC'] = abs(df['low'] - df['close'].shift(1))

    df['TR'] = df[['HL', 'HC', 'LC']].max(axis=1)
    df['ATR'] = df['TR'].ewm(span=int(p['atr_window']), adjust=False).mean()

    df['TP'] = df['ATR'] * p['atr_m']

    return df


# -------- BACKTEST --------
def run_backtest(df, strategy, p):

    df = prepare_data(df, p)
    x_days = int(p['x_days'])

    trades = []
    trade_log = []

    for i in range(1, len(df) - 1):

        row = df.iloc[i]
        prev = df.iloc[i - 1]

        if strategy == "Doji":
            body = abs(row['close'] - row['open'])
            rng = row['high'] - row['low']
            cond = (rng > 0 and body / rng < p['doji_threshold'])
        else:
            cond = (row['close'] > prev['close'])

        if not cond:
            continue

        entry = row['close']
        entry_date = row['datetime']

        # -------- SL (DOJI LOW BASED) --------
        sl_price = row['low']
        sl_points = entry - sl_price

        tp_points = max(row['TP'], 100)
        tp_price = entry + tp_points

        result = None
        exit_date = None
        exit_price = None

        for j in range(i+1, min(i+1 + x_days, len(df))):

            high = df.iloc[j]['high']
            low = df.iloc[j]['low']

            if high >= tp_price:
                result = tp_points
                exit_price = tp_price
                exit_date = df.iloc[j]['datetime']
                break

            if low <= sl_price:
                result = -sl_points
                exit_price = sl_price
                exit_date = df.iloc[j]['datetime']
                break

        if result is not None:
            trades.append(result)

            trade_log.append({
                "entry_date": entry_date,
                "exit_date": exit_date,
                "entry_price": entry,
                "exit_price": exit_price,
                "pnl": result
            })

    if len(trades) == 0:
        return 0, 0, 0, pd.Series(), pd.Series(), pd.DataFrame()

    pnl_series = pd.Series(trades)

    trade_df = pd.DataFrame(trade_log)
    trade_df['entry_date'] = pd.to_datetime(trade_df['entry_date'])

    equity = pnl_series.cumsum()
    equity.index = trade_df['entry_date']

    return pnl_series.sum(), len(trades), (pnl_series > 0).mean(), equity, pnl_series, trade_df


# -------- UI --------
def show_manual_simulator():

    st.title("⚙️ Manual Strategy Tester")

    c1, c2 = st.columns(2)

    with c1:
        stock = st.text_input("Stock", "RELIANCE")
        days = st.number_input("Days", 100, 1500, 500)

    with c2:
        strategy = st.selectbox("Strategy", ["Doji", "BE"])

    st.markdown("### 🎯 Strategy Parameters")

    p1, p2, p3, p4 = st.columns(4)

    with p1:
        doji_threshold = st.number_input("Doji Threshold", 0.1, 0.5, 0.2)

    with p2:
        atr_window = st.number_input("ATR Window", 3, 20, 7)

    with p3:
        atr_m = st.number_input("TP Multiplier", 0.5, 3.0, 1.5)

    with p4:
        x_days = st.number_input("Holding Days", 1, 10, 5)

    if st.button("Run Manual Test"):

        df = get_stock_data(stock, days)

        if df is None:
            st.error("❌ Data fetch failed")
            return

        p = {
            "doji_threshold": doji_threshold,
            "atr_window": atr_window,
            "atr_m": atr_m,
            "x_days": x_days
        }

        pnl, trades, win, equity, pnl_series, trade_df = run_backtest(df, strategy, p)

        st.subheader("📊 Performance")

        c1, c2, c3 = st.columns(3)
        c1.metric("PnL", round(pnl, 2), delta_color="inverse")
        c2.metric("Trades", trades)
        c3.metric("Win %", round(win * 100, 2))

        if not equity.empty:

            fig = go.Figure()

            fig.add_trace(go.Scatter(
                x=equity.index,
                y=equity.values,
                mode='lines',
                name='Equity'
            ))

            fig.add_trace(go.Scatter(
                x=trade_df['entry_date'],
                y=equity.values,
                mode='markers',
                name='Entry',
                marker=dict(symbol='triangle-up', size=8)
            ))

            fig.add_trace(go.Scatter(
                x=trade_df['exit_date'],
                y=equity.values,
                mode='markers',
                name='Exit',
                marker=dict(symbol='triangle-down', size=8)
            ))

            st.plotly_chart(fig, use_container_width=True)

        st.subheader("📋 Trade Log")
        st.dataframe(trade_df)