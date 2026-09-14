import os
import sys
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import backtest as bt
import strategies as st

UNIVERSE = os.path.join(bt.DATA_DIR, "universe.csv")


def build(symbols, interval):
    close = bt.price_panel(symbols, interval, "close")
    high = bt.price_panel(symbols, interval, "high")
    low = bt.price_panel(symbols, interval, "low")
    keep = close.columns[close.notna().sum() > 250]
    return close[keep], high[keep], low[keep]


def run(interval="1d", n_symbols=45, target_dd=0.40):
    uni = pd.read_csv(UNIVERSE)["symbol"].tolist()[:n_symbols]
    close, high, low = build(uni, interval)
    ret = close.pct_change().fillna(0.0)
    ppy = bt.PERIODS_PER_YEAR[interval]
    funding = bt.funding_daily_panel(list(close.columns), close.index) if interval == "1d" else None
    print(f"\n=== SCREEN | {interval} | {close.shape[1]} assets | "
          f"{close.index.min().date()} -> {close.index.max().date()} | target DD {target_dd:.0%} ===")

    rows = []

    def add(name, w, fee_bps=5.0, slip_bps=2.0, funding_panel=None):
        r = bt.portfolio_backtest(ret, w, funding=funding_panel, leverage_cap=1.0,
                                  asset_cap=1.0, fee_bps=fee_bps, slip_bps=slip_bps, ppy=ppy)
        net = r["net"]
        m = bt.metrics(net, ppy)
        sm = bt.scaled_metrics(net, target_dd=target_dd, ppy=ppy)
        rows.append({
            "strategy": name, "sharpe": m["sharpe"], "maxdd_1x": m["max_dd"],
            "cagr_1x": m["cagr"], "scale": sm["scale"], "cagr_at_dd": sm["cagr"],
            "maxdd_at_dd": sm["max_dd"], "calmar": sm["calmar"],
            "turnover": r["turnover"].mean(), "funding_pnl": r["funding"].mean() * ppy,
        })

    zeros = pd.DataFrame(0.0, index=close.index, columns=close.columns)
    if "BTCUSDT" in close.columns:
        add("BUY&HOLD BTC", zeros.assign(BTCUSDT=1.0), fee_bps=0, slip_bps=0)
    add("EQUAL-WEIGHT BASKET LONG", zeros + 1.0 / close.shape[1], fee_bps=0, slip_bps=0)

    add("TSMOM 30d", st.tsmom(close, 30))
    add("TSMOM 90d", st.tsmom(close, 90))
    add("MA cross 20/60", st.ma_cross(close, 20, 60))
    add("MA cross 50/200", st.ma_cross(close, 50, 200))
    add("Donchian 55", st.donchian(close, high, low, 55))
    add("Donchian 20", st.donchian(close, high, low, 20))
    add("MeanRev 7d", st.mean_reversion(close, 7))
    add("XS Mom 30d k5", st.xs_momentum(close, 30, 5))
    add("XS Mom 60d k5", st.xs_momentum(close, 60, 5))
    add("XS Rev 7d k5", st.xs_reversal(close, 7, 5))
    add("XS Rev 3d k5", st.xs_reversal(close, 3, 5))
    if funding is not None:
        add("Funding carry LS k5", st.funding_carry(funding, 5), funding_panel=funding)
        add("Funding carry LS k10", st.funding_carry(funding, 10), funding_panel=funding)
        add("Funding short-only k5", st.carry_short_only(funding, 5), funding_panel=funding)

    df = pd.DataFrame(rows)
    show = df.copy()
    for c in ["maxdd_1x", "cagr_1x", "cagr_at_dd", "maxdd_at_dd", "funding_pnl"]:
        show[c] = (show[c] * 100).round(2)
    for c in ["sharpe", "calmar", "scale", "turnover"]:
        show[c] = show[c].round(2)
    show = show.sort_values("sharpe", ascending=False)
    print(show.to_string(index=False))
    df.to_csv(os.path.join(bt.DATA_DIR, f"screen_{interval}.csv"), index=False)
    return df


if __name__ == "__main__":
    interval = sys.argv[1] if len(sys.argv) > 1 else "1d"
    run(interval=interval)
