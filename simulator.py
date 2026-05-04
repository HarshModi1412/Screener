import streamlit as st
import pandas as pd
import numpy as np
from tvDatafeed import TvDatafeed, Interval
import plotly.graph_objects as go
from itertools import product

# -------- CONFIG --------
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

    p['atr_window'] = int(p.get('atr_window', 7))

    df['HL'] = df['high'] - df['low']
    df['HC'] = abs(df['high'] - df['close'].shift(1))
    df['LC'] = abs(df['low'] - df['close'].shift(1))

    df['TR'] = df[['HL', 'HC', 'LC']].max(axis=1)
    df['ATR'] = df['TR'].ewm(span=p['atr_window'], adjust=False).mean()

    df['TP'] = df['ATR'] * p.get('atr_m', 1.5)

    return df


# -------- BACKTEST --------
def run_backtest(df, strategy, p):

    df = prepare_data(df, p)
    x_days = int(p.get('x_days', 5))

    trades = []
    trade_log = []

    for i in range(1, len(df) - 1):

        row = df.iloc[i]
        prev = df.iloc[i - 1]

        # -------- SIGNAL --------
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

        # -------- STOP LOSS (CORRECT) --------
        sl_points = row['high'] - row['low']
        sl_price = entry - sl_points

        # -------- TAKE PROFIT --------
        tp_points = max(row['TP'], 100)
        tp_price = entry + tp_points

        exit_price = None
        exit_date = None
        result = None

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
                "entry_price": entry,
                "exit_date": exit_date,
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


# -------- OPTIMIZER --------
def optimize(df, strategy):

    param_grid = {
        "doji_threshold": [0.2, 0.3],
        "atr_window": [5, 7],
        "atr_m": [1, 1.5],
        "x_days": [3, 5]
    }

    results = []

    for values in product(*param_grid.values()):
        p = dict(zip(param_grid.keys(), values))

        pnl, trades, win, _, _, _ = run_backtest(df, strategy, p)

        results.append({
            "pnl": pnl,
            "trades": trades,
            "win": win,
            "score": pnl + (win * 100),
            **p
        })

    df_res = pd.DataFrame(results)
    best = df_res.sort_values("score", ascending=False).iloc[0]

    return best.to_dict(), df_res


# -------- DRAWdown --------
def drawdown(eq):
    return (eq - eq.cummax()).min()


# -------- UI --------
def show_simulator():

    st.title("🧠 Strategy Simulator")

    c1, c2 = st.columns(2)

    with c1:
        stock = st.text_input("Stock", "RELIANCE")
        days = st.number_input("Days", 100, 1500, 500)

    with c2:
        strategy = st.selectbox("Strategy", ["Doji", "BE"])
        split = st.slider("Train %", 50, 90, 70)

    if st.button("Run Simulation"):

        df = get_stock_data(stock, days)

        if df is None:
            st.error("❌ Data fetch failed")
            return

        st.dataframe(df.head())

        split_idx = int(len(df) * split / 100)
        train = df.iloc[:split_idx]
        test = df.iloc[split_idx:]

        best, all_results = optimize(train, strategy)

        st.subheader("🏆 Best Params")
        st.json(best)

        pnl, trades, win, equity, pnl_series, trade_df = run_backtest(test, strategy, best)

        st.subheader("📊 Performance")

        col1, col2, col3 = st.columns(3)
        col1.metric("PnL", round(pnl, 2), delta_color="inverse")
        col2.metric("Trades", trades)
        col3.metric("Win %", round(win * 100, 2))

        # -------- PLOT --------
        if not equity.empty:

            fig = go.Figure()

            # Equity
            fig.add_trace(go.Scatter(
                x=equity.index,
                y=equity.values,
                mode='lines',
                name='Equity'
            ))

            # Entry markers
            fig.add_trace(go.Scatter(
                x=trade_df['entry_date'],
                y=equity.values,
                mode='markers',
                name='Entry',
                marker=dict(size=8, symbol='triangle-up')
            ))

            # Exit markers
            fig.add_trace(go.Scatter(
                x=trade_df['exit_date'],
                y=equity.values,
                mode='markers',
                name='Exit',
                marker=dict(size=8, symbol='triangle-down')
            ))

            st.plotly_chart(fig, use_container_width=True)

            st.metric("Max Drawdown", round(drawdown(equity), 2))

        st.subheader("📋 Trade Log")
        st.dataframe(trade_df)