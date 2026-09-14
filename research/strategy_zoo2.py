import os
import sys
import glob
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass
import backtest as bt
import strategy_zoo as sz

SPLIT = pd.Timestamp("2024-01-01")
PPY = 365
K = 10


def load_full():
    closes, vols, highs, lows = {}, {}, {}, {}
    qav, tbqav, ntr = {}, {}, {}
    for path in glob.glob(os.path.join(bt.DATA_DIR, "*_1df.csv")):
        sym = os.path.basename(path)[:-8]
        if not sym.endswith("USDT") or "SETTLED" in sym:
            continue
        try:
            df = pd.read_csv(path)
        except Exception:
            continue
        if len(df) < 60 or "close" not in df.columns:
            continue
        df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True, format="ISO8601").dt.tz_localize(None)
        df = df.drop_duplicates("timestamp").set_index("timestamp").sort_index()
        closes[sym] = pd.to_numeric(df["close"], errors="coerce")
        vols[sym] = pd.to_numeric(df["volume"], errors="coerce")
        if "high" in df.columns:
            highs[sym] = pd.to_numeric(df["high"], errors="coerce")
            lows[sym] = pd.to_numeric(df["low"], errors="coerce")
        if "qav" in df.columns:
            qav[sym] = pd.to_numeric(df["qav"], errors="coerce")
            tbqav[sym] = pd.to_numeric(df["tbqav"], errors="coerce")
            ntr[sym] = pd.to_numeric(df["num_trades"], errors="coerce")
    close = pd.DataFrame(closes).sort_index()
    idx = close.index
    return (close,
            pd.DataFrame(vols).reindex(idx),
            pd.DataFrame(highs).reindex(idx),
            pd.DataFrame(lows).reindex(idx),
            pd.DataFrame(qav).reindex(idx),
            pd.DataFrame(tbqav).reindex(idx),
            pd.DataFrame(ntr).reindex(idx))


def zrow(df, mask):
    return sz.zs(df, mask)


def main():
    (close, volume, high, low, qav, tbqav, ntr) = load_full()
    mask = sz.pit_mask(close, volume)
    fund = sz.funding_panel(close)
    ret = close.pct_change()
    vol30 = ret.rolling(30).std()
    dvol = close * volume
    mkt = ret.mean(axis=1)
    oh = mask.sum(axis=1)[mask.sum(axis=1) > 0].mean()
    print(f"panel {close.shape[1]} symbols | order-flow cols on {qav.shape[1]} | avg PIT universe {oh:.1f}\n")

    mom_stack = sum(close / close.shift(lb) - 1.0 for lb in (14, 21, 30, 45, 60)) / 5.0
    f7 = fund.rolling(7).mean()
    btc = close["BTCUSDT"] if "BTCUSDT" in close.columns else close.mean(axis=1)
    btc_ret = btc.pct_change()
    btc_mom5 = btc / btc.shift(5) - 1.0
    btc_ma200 = btc.rolling(200).mean()

    tbr = (tbqav / qav.replace(0, np.nan)).clip(0.2, 0.8)
    tbr_z = zrow(tbr.rolling(5).mean(), mask)
    tbr_chg = tbr.rolling(3).mean() - tbr.rolling(20).mean()
    trades_z = zrow(np.log1p(ntr.rolling(5).mean()), mask)
    amihud = ((ret.abs() / dvol.replace(0, np.nan)).rolling(20).mean())

    beta = ret.rolling(60).corr(btc_ret).mul(vol30.div(ret.rolling(60).std(), fill_value=np.nan)).fillna(1.0)

    signals = {}
    S = signals

    S["[ref] mom - funding tilt"] = lambda: sz.xs(zrow(mom_stack / vol30, mask) - zrow(f7, mask), mask)
    S["[ref] momentum baseline"] = lambda: sz.xs(mom_stack / vol30, mask)

    S["OFI taker-buy z"] = lambda: sz.xs(tbr_z, mask)
    S["OFI change 3v20"] = lambda: sz.xs(tbr_chg, mask)
    S["OFI divergence (buy vs price)"] = lambda: sz.xs(tbr_z - zrow(mom_stack / vol30, mask), mask)
    S["OFI contrarian"] = lambda: sz.xs(-tbr_z, mask)
    S["trade-count z"] = lambda: sz.xs(trades_z, mask)
    S["Amihud illiquidity"] = lambda: sz.xs(amihud, mask)
    S["illiquidity premium (long illiquid)"] = lambda: sz.xs(amihud, mask, k=10)
    S["liquidity factor (short liquid)"] = lambda: sz.xs(-np.log1p(dvol.rolling(20).mean()), mask)

    max20 = ret.rolling(20).max()
    S["MAX lottery (short high max)"] = lambda: sz.xs(-max20, mask)
    S["skewness (short positive)"] = lambda: sz.xs(-ret.rolling(20).skew(), mask)
    S["kurtosis (short fat tails)"] = lambda: sz.xs(-ret.rolling(20).kurt(), mask)

    S["long-term reversal 120d"] = lambda: sz.xs(-(close / close.shift(120) - 1.0), mask)
    S["long-term reversal 180d"] = lambda: sz.xs(-(close / close.shift(180) - 1.0), mask)

    catchup = (beta.mul(btc_mom5, axis=0) - (close / close.shift(5) - 1.0))
    S["BTC lead-lag catch-up"] = lambda: sz.xs(catchup, mask)
    S["low beta (defensive)"] = lambda: sz.xs(-beta, mask)

    fz = zrow(f7, mask)
    S["funding contrarian extremes"] = lambda: sz.xs(-fz * (fz.abs() > 2).astype(float), mask)
    S["funding change 3v20"] = lambda: sz.xs(-(f7.rolling(3).mean() - f7.rolling(20).mean()), mask)

    regime_ts = (btc > btc_ma200).astype(float)
    S["mom + BTC regime filter"] = lambda: sz.xs(mom_stack / vol30, mask).mul(regime_ts, axis=0)
    mkt_vol = ret.mean(axis=1).rolling(30).std()
    vol_reg = (0.03 / mkt_vol).clip(upper=1.5).fillna(1.0)
    S["mom + market-vol scaling"] = lambda: sz.xs(mom_stack / vol30, mask).mul(vol_reg, axis=0)

    S["STACK mom+OFI"] = lambda: sz.xs(zrow(mom_stack / vol30, mask) + zrow(tbr_z, mask), mask)
    S["STACK mom+OFI+funding"] = lambda: sz.xs(zrow(mom_stack / vol30, mask) + zrow(tbr_z, mask) - zrow(f7, mask), mask)
    S["STACK mom+OFI+funding+lowvol"] = lambda: sz.xs(
        zrow(mom_stack / vol30, mask) + zrow(tbr_z, mask) - zrow(f7, mask) - 0.5 * zrow(vol30, mask), mask)
    S["STACK everything"] = lambda: sz.xs(
        zrow(mom_stack / vol30, mask) + zrow(tbr_z, mask) - zrow(f7, mask) - 0.5 * zrow(vol30, mask)
        - 0.5 * zrow(max20, mask), mask)

    rows = []
    for name, fn in signals.items():
        try:
            w = fn()
            r = bt.portfolio_backtest(ret.fillna(0.0), w, funding=fund, leverage_cap=1.0,
                                      asset_cap=1.0, fee_bps=5.0, slip_bps=2.0, ppy=PPY)
            net = r["net"]
            rows.append({
                "strategy": name,
                "is_sharpe": bt.metrics(net[net.index < SPLIT], PPY)["sharpe"],
                "oos_sharpe": bt.metrics(net[net.index >= SPLIT], PPY)["sharpe"],
                "full_sharpe": bt.metrics(net, PPY)["sharpe"],
                "cagr": bt.metrics(net, PPY)["cagr"] * 100,
                "dd": bt.metrics(net, PPY)["max_dd"] * 100,
                "at40dd": bt.scaled_metrics(net, 0.40, PPY)["cagr"] * 100,
                "turn": r["turnover"].mean(),
            })
        except Exception as e:
            print(f"  !! {name}: {e}")
    df = pd.DataFrame(rows)[["strategy", "is_sharpe", "oos_sharpe", "full_sharpe",
                             "cagr", "dd", "at40dd", "turn"]]
    df.to_csv(os.path.join(bt.DATA_DIR, "strategy_zoo2.csv"), index=False)
    print(f"=== WAVE 2: {len(df)} signals, ranked by IS Sharpe ===")
    print(df.sort_values("is_sharpe", ascending=False).round(2).to_string(index=False))
    print("\n=== top by OOS Sharpe ===")
    print(df.sort_values("oos_sharpe", ascending=False).head(8).round(2).to_string(index=False))
    print("\n=== consistent (IS>0.5 and OOS>0.5), sorted by full Sharpe ===")
    g = df[(df.is_sharpe > 0.5) & (df.oos_sharpe > 0.5)].sort_values("full_sharpe", ascending=False)
    print(g.round(2).to_string(index=False) if len(g) else "  none")


if __name__ == "__main__":
    main()
