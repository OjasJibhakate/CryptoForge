import os
import sys
import json
import numpy as np
import pandas as pd
import streamlit as st
import plotly.graph_objects as go

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from paper import config as cfg, market

st.set_page_config(page_title="CryptoForge Paper Desk", layout="wide",
                   initial_sidebar_state="expanded")

st.markdown("""
<style>
.block-container { padding-top: 2rem; }
div[data-testid="stMetricValue"] { font-size: 1.4rem; }
</style>
""", unsafe_allow_html=True)


def read_csv(path):
    if os.path.exists(path) and os.path.getsize(path) > 3:
        try:
            return pd.read_csv(path, encoding="utf-8")
        except Exception:
            return pd.DataFrame()
    return pd.DataFrame()


def load_account(profile):
    p = cfg.files(profile)["account"]
    if os.path.exists(p):
        with open(p, encoding="utf-8") as f:
            return json.load(f)
    return None


@st.cache_data(ttl=60)
def live_prices(symbols):
    try:
        return market.live_prices(symbols) if symbols else {}
    except Exception:
        return {}


st.sidebar.title("CryptoForge Paper Desk")
profile = st.sidebar.radio("Account", list(cfg.PROFILES),
                           format_func=lambda p: cfg.cfg_for(p)["label"])
if st.sidebar.button("Refresh now"):
    st.cache_data.clear()
    st.rerun()
st.sidebar.markdown("---")
st.sidebar.metric("Initial capital", f"${cfg.INITIAL_CAPITAL:,.0f} per account")
st.sidebar.info("Dollar-neutral cross-sectional momentum on Binance USDT-M perps. "
                "Two accounts run side by side: the original baseline, and the upgraded "
                "wave3 (funding tilt + soft BTC regime). Virtual money, no exchange orders.")

st.title("CRYPTOFORGE :: PAPER TRADING DESK")
st.caption("Three desks: baseline momentum vs wave3 (funding tilt + regime + risk management) "
           "vs a replay of a Binance lead trader's actual trades.")

# ---------- A/B overview ----------
overview = []
for p in cfg.PROFILES:
    d = read_csv(cfg.files(p)["daily"])
    a = load_account(p)
    if a is None or d.empty:
        overview.append({"account": p, "equity": None, "ret_%": None, "runs": 0})
        continue
    eq = float(d["equity"].iloc[-1])
    overview.append({"account": p, "label": cfg.cfg_for(p)["label"],
                     "equity": eq, "ret_%": (eq / a["initial_capital"] - 1) * 100,
                     "maxDD_%": (d["equity"] / d["equity"].cummax() - 1).min() * 100,
                     "runs": a.get("runs", len(d))})
ov = pd.DataFrame(overview)
cols = st.columns(len(cfg.PROFILES))
for col, row in zip(cols, ov.to_dict("records")):
    with col:
        st.subheader(row["account"])
        if row.get("equity") is None:
            st.info("No runs yet.")
        else:
            st.metric(row["label"], f"${row['equity']:,.2f}", f"{row['ret_%']:+.2f}%")
            st.caption(f"runs {row['runs']} · max DD {row['maxDD_%']:.2f}%")

fig_cmp = go.Figure()
for p in cfg.PROFILES:
    d = read_csv(cfg.files(p)["daily"])
    if d.empty:
        continue
    fig_cmp.add_trace(go.Scatter(x=pd.to_datetime(d["date"]), y=d["equity"], mode="lines+markers",
                                 name=cfg.cfg_for(p)["label"]))
fig_cmp.add_hline(y=cfg.INITIAL_CAPITAL, line_dash="dash", line_color="#888")
fig_cmp.update_layout(template="plotly_dark", height=320, margin=dict(l=10, r=10, t=30, b=10),
                      yaxis_title="Equity ($)", hovermode="x unified")
st.plotly_chart(fig_cmp, width="stretch")
st.markdown("---")

# ---------- selected account detail ----------
acc = load_account(profile)
daily = read_csv(cfg.files(profile)["daily"])
trades = read_csv(cfg.files(profile)["trades"])
events = read_csv(cfg.files(profile)["events"])

if acc is None or daily.empty:
    st.warning(f"No runs yet for **{profile}**. Start it with:  "
               f"`py -m paper.engine --profile {profile} --force`")
    st.stop()

initial = acc["initial_capital"]
equity = daily["equity"].astype(float)
dates = pd.to_datetime(daily["date"])
last_eq = float(equity.iloc[-1])
pnl = last_eq - initial
ret = pnl / initial
rets = equity.pct_change().dropna()
sharpe = (rets.mean() / rets.std() * np.sqrt(365)) if len(rets) > 1 and rets.std() > 0 else 0.0
max_dd = float((equity / equity.cummax() - 1).min())
days = int(np.ceil((pd.Timestamp.now(tz="UTC").tz_localize(None)
                    - pd.to_datetime(acc["start_utc"])).days)) or 1

st.header(f"{profile} — {acc.get('label','')}")
c1, c2, c3, c4, c5 = st.columns(5)
c1.metric("Equity", f"${last_eq:,.2f}", f"{ret*100:+.2f}%")
c2.metric("Net P&L", f"${pnl:,.2f}")
c3.metric("Max drawdown", f"{max_dd*100:.2f}%")
c4.metric("Sharpe (ann.)", f"{sharpe:.2f}")
c5.metric("Runs / days", f"{acc.get('runs', len(daily))} / {days}")

if acc.get("breaker_active"):
    st.error("CIRCUIT BREAKER ACTIVE — gross exposure reduced.")
st.caption(f"started {acc['start_utc']} UTC · last run {acc.get('last_run_utc')} · "
           f"window {cfg.EXPERIMENT_DAYS} days")

tab1, tab2, tab3, tab4 = st.tabs(["Equity & Drawdown", "Positions", "Trade Log", "Daily / Events"])

with tab1:
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=dates, y=equity, mode="lines+markers", name="Equity",
                             line=dict(color="#00e5a0", width=3)))
    fig.add_hline(y=initial, line_dash="dash", line_color="#888",
                  annotation_text=f"Start ${initial:,.0f}", annotation_position="bottom right")
    fig.update_layout(template="plotly_dark", height=400, margin=dict(l=10, r=10, t=30, b=10),
                      xaxis_title="Date", yaxis_title="Equity ($)", hovermode="x unified")
    st.plotly_chart(fig, width="stretch")

    dd = equity / equity.cummax() - 1.0
    dd_fig = go.Figure()
    dd_fig.add_trace(go.Scatter(x=dates, y=dd * 100, fill="tozeroy",
                                line=dict(color="#ff4b4b"), name="Drawdown %"))
    dd_fig.add_hline(y=-cfg.cfg_for(profile)["dd_breaker_trigger"] * 100, line_dash="dot",
                     line_color="#ffb703", annotation_text="circuit breaker")
    dd_fig.update_layout(template="plotly_dark", height=240, margin=dict(l=10, r=10, t=30, b=10),
                         yaxis_title="Drawdown (%)")
    st.plotly_chart(dd_fig, width="stretch")
    st.caption("30 days is far too short to judge an edge. Backtest reference for wave3: "
               "Sharpe ~1.57, max DD ~-29%, ~77% CAGR at a 40% drawdown budget.")

with tab2:
    pos = acc.get("positions", {})
    if not pos:
        st.info("No open positions.")
    else:
        px = live_prices(tuple(sorted(set(pos) | set(acc.get("avg_entry", {})))))
        rows_p = []
        for s, q in pos.items():
            p = px.get(s)
            avg = acc.get("avg_entry", {}).get(s, 0.0)
            notional = q * p if p else None
            upnl = q * (p - avg) if (p and avg) else None
            rows_p.append({"symbol": s, "side": "LONG" if q > 0 else "SHORT", "qty": q,
                           "avg_entry": avg, "price": p, "notional": notional,
                           "weight_%": (notional / last_eq * 100) if notional else None,
                           "unrealized_pnl": upnl,
                           "pnl_%": ((p / avg - 1) * 100 * (1 if q > 0 else -1)) if (p and avg) else None})
        pdf = pd.DataFrame(rows_p).sort_values(["side", "notional"], ascending=[True, False])
        st.markdown(f"**{(pdf.side=='LONG').sum()} longs · {(pdf.side=='SHORT').sum()} shorts · "
                    f"gross ${pdf['notional'].abs().sum():,.0f} "
                    f"({pdf['notional'].abs().sum()/last_eq*100:.0f}% of equity) · "
                    f"net ${pdf['notional'].sum():,.0f}**")
        show = pdf.copy()
        for c in ["qty", "avg_entry", "price"]:
            show[c] = show[c].map(lambda v: f"{v:,.6f}" if isinstance(v, (int, float)) and v else v)
        for c in ["notional", "unrealized_pnl"]:
            show[c] = show[c].map(lambda v: f"${v:,.2f}" if isinstance(v, (int, float)) else v)
        for c in ["weight_%", "pnl_%"]:
            show[c] = show[c].map(lambda v: f"{v:+.2f}%" if isinstance(v, (int, float)) else v)
        st.dataframe(show, width="stretch", hide_index=True)

with tab3:
    if trades.empty:
        st.info("No trades recorded yet.")
    else:
        t = trades.copy()
        t["timestamp"] = pd.to_datetime(t["timestamp"])
        st.markdown(f"**{len(t)} fills · fees ${t['fee'].sum():,.2f} · slippage ${t['slippage'].sum():,.2f}**")
        st.dataframe(t.sort_values("timestamp", ascending=False), width="stretch", hide_index=True)
        st.download_button("Download trades CSV", t.to_csv(index=False), f"{profile}_trades.csv", "text/csv")

with tab4:
    c1, c2 = st.columns(2)
    with c1:
        st.subheader("Daily snapshots")
        d = daily.copy()
        d["equity"] = d["equity"].map(lambda v: f"${v:,.2f}")
        d["funding_pnl"] = d["funding_pnl"].map(lambda v: f"${v:+.4f}")
        d["drawdown"] = d["drawdown"].map(lambda v: f"{v*100:.2f}%")
        d["return_pct"] = d["return_pct"].map(lambda v: f"{v*100:+.2f}%")
        st.dataframe(d, width="stretch", hide_index=True)
    with c2:
        st.subheader("Events")
        if events.empty:
            st.info("No risk events.")
        else:
            st.dataframe(events.sort_values("timestamp", ascending=False), width="stretch", hide_index=True)
        st.subheader("Account")
        st.json({k: v for k, v in acc.items() if k != "positions"})
