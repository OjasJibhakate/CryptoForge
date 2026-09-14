import os
import sys
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import backtest as bt
import strategies as st
import carry as cy

UNIVERSE = os.path.join(bt.DATA_DIR, "universe.csv")
SPLIT = pd.Timestamp("2024-01-01")


def metrics_both(net, ppy):
    ins = bt.metrics(net[net.index < SPLIT], ppy)
    oos = bt.metrics(net[net.index >= SPLIT], ppy)
    return ins, oos


def main(interval="1d"):
    uni = pd.read_csv(UNIVERSE)["symbol"].tolist()[:45]
    close = bt.price_panel(uni, interval, "close")
    high = bt.price_panel(uni, interval, "high")
    low = bt.price_panel(uni, interval, "low")
    keep = close.columns[close.notna().sum() > 250]
    close, high, low = close[keep], high[keep], low[keep]
    ret = close.pct_change().fillna(0.0)
    ppy = bt.PERIODS_PER_YEAR[interval]
    funding = bt.funding_daily_panel(list(keep), close.index) if interval == "1d" else None

    def wbt(w, f=None):
        r = bt.portfolio_backtest(ret, w, funding=f, leverage_cap=1.0, asset_cap=1.0, ppy=ppy)
        return r["net"]

    strategies = {
        "TSMOM 30d": wbt(st.tsmom(close, 30)),
        "TSMOM 20d": wbt(st.tsmom(close, 20)),
        "MA 10/30": wbt(st.ma_cross(close, 10, 30)),
        "Donchian 20": wbt(st.donchian(close, high, low, 20)),
        "XS Mom 30d": wbt(st.xs_momentum(close, 30, 5)),
        "XS Rev 7d": wbt(st.xs_reversal(close, 7, 5)),
        "MeanRev 7d": wbt(st.mean_reversion(close, 7)),
    }
    if funding is not None:
        net, _ = cy.funding_harvest(funding, lookback=7, max_assets=10, min_rate=0.0)
        strategies["Funding harvest"] = net

    rows = []
    for name, net in strategies.items():
        ins, oos = metrics_both(net, ppy)
        rows.append({
            "strategy": name,
            "IS_sharpe": ins["sharpe"], "IS_cagr": ins["cagr"] * 100, "IS_dd": ins["max_dd"] * 100,
            "OOS_sharpe": oos["sharpe"], "OOS_cagr": oos["cagr"] * 100, "OOS_dd": oos["max_dd"] * 100,
            "degrade": ins["sharpe"] - oos["sharpe"],
        })
    df = pd.DataFrame(rows).sort_values("IS_sharpe", ascending=False)
    print(f"\n=== HOLDOUT: IS = <{SPLIT.date()} | OOS = >={SPLIT.date()} | {interval} ===")
    print(df.round(2).to_string(index=False))
    df.to_csv(os.path.join(bt.DATA_DIR, f"holdout_{interval}.csv"), index=False)
    return df


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "1d")
