import os
import re
import sys
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PATH = os.path.join(ROOT, "binance_trades.md")


def num(s):
    if s is None:
        return np.nan
    s = str(s).replace(",", "").replace("USDT", "").replace("+", "").strip()
    m = re.search(r"-?\d+\.?\d*", s)
    return float(m.group()) if m else np.nan


def parse(path):
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        lines = [l.strip() for l in f.readlines()]
    opens = [i for i, l in enumerate(lines) if l == "Opened"]
    trades = []
    for k, i in enumerate(opens):
        end = opens[k + 1] if k + 1 < len(opens) else len(lines)   # bound the scan
        rec = {"opened": lines[i + 1] if i + 1 < end else None}
        for j in range(i + 1, end):
            if lines[j] == "Entry Price":
                rec["entry"] = num(lines[j + 1])
            elif lines[j] == "Max. Open Interest":
                rec["size_raw"] = lines[j + 1]
            elif lines[j] == "Closing PNL":
                rec["pnl"] = num(lines[j + 1])
            elif lines[j] == "Avg. Close Price":
                rec["close"] = num(lines[j + 1])
            elif lines[j] == "Closed" and j + 1 < end and re.match(r"^\d{4}-\d{2}-\d{2}", lines[j + 1]):
                rec["closed"] = lines[j + 1]
        for j in range(i - 1, max(i - 14, -1), -1):
            if lines[j] in ("Short", "Long") and "side" not in rec:
                rec["side"] = lines[j]
            if re.match(r"^\d+x$", lines[j]) and "lev" not in rec:
                rec["lev"] = int(lines[j].rstrip("x"))
            if lines[j].endswith("USDT") and "symbol" not in rec:
                rec["symbol"] = lines[j]
        trades.append(rec)
    df = pd.DataFrame(trades)
    for c in ["entry", "close", "pnl"]:
        df[c] = pd.to_numeric(df.get(c), errors="coerce")
    df["opened"] = pd.to_datetime(df["opened"], errors="coerce")
    df["closed"] = pd.to_datetime(df["closed"], errors="coerce")
    df["hold_s"] = (df["closed"] - df["opened"]).dt.total_seconds()
    df["size"] = df["size_raw"].map(num)
    df["notional"] = df["size"] * df["entry"]
    return df


def main():
    df = parse(PATH).dropna(subset=["pnl"]).reset_index(drop=True)
    bad = (df["hold_s"] < 0).sum()
    print(f"parsed {len(df)} trades | unparseable close-time: {bad} ({bad/len(df)*100:.1f}%)")
    print(f"period : {df['opened'].min()} -> {df['closed'].max()}")
    span = (df["opened"].max() - df["opened"].min()).days
    print(f"span   : {span} days ({span/30.4:.1f} months)  <-- note: NOT one year")
    print(f"symbols: {df['symbol'].nunique()} | sides {df['side'].value_counts().to_dict()}")
    print(f"lev    : {df['lev'].value_counts().sort_index().to_dict()}")

    w, l = df["pnl"] > 0, df["pnl"] < 0
    print(f"\n=== WINS / LOSSES ===")
    print(f"win rate      {w.mean()*100:.2f}%   ({w.sum()}W / {l.sum()}L / {(~w&~l).sum()} flat)")
    print(f"total PNL     {df['pnl'].sum():+,.2f} USDT")
    print(f"profit factor {df.loc[w,'pnl'].sum()/abs(df.loc[l,'pnl'].sum()):.2f}")
    print(f"avg win {df.loc[w,'pnl'].mean():+.2f}  | avg loss {df.loc[l,'pnl'].mean():+.2f}  "
          f"| ratio {abs(df.loc[w,'pnl'].mean()/df.loc[l,'pnl'].mean()):.2f}")
    aw, al = df.loc[w, "pnl"].mean(), abs(df.loc[l, "pnl"].mean())
    print(f"breakeven win rate needed at this R:R: {al/(aw+al)*100:.1f}%  (actual {w.mean()*100:.1f}%)")

    print(f"\n=== LOSS CONCENTRATION (the whole story) ===")
    tot_loss = abs(df.loc[l, "pnl"].sum())
    for _, r in df.nsmallest(4, "pnl").iterrows():
        print(f"  {str(r['closed'])[:19]}  {r['symbol']:<14} {r['side']:<5} {r['lev']}x  "
              f"pnl {r['pnl']:+8.2f}  = {abs(r['pnl'])/tot_loss*100:5.1f}% of all losses")
    print(f"  -> the single largest loss is {abs(df['pnl'].min())/df.loc[w,'pnl'].mean():.1f}x the average win")

    print(f"\n=== HOLDING TIME (now bounded) ===")
    ok = df[df["hold_s"] >= 0]
    if len(ok):
        print(f"  wins    median {ok.loc[ok.pnl>0,'hold_s'].median():8.0f}s")
        print(f"  losses  median {ok.loc[ok.pnl<0,'hold_s'].median():8.0f}s")
        print(f"  ALL     median {ok['hold_s'].median():8.0f}s   max {ok['hold_s'].max():.0f}s "
              f"({ok['hold_s'].max()/3600:.1f}h)")
        print(f"  share of trades held < 5 minutes: {(ok['hold_s']<300).mean()*100:.1f}%")

    print(f"\n=== POSITION SIZING: martingale check ===")
    print(f"  median notional  wins {df.loc[w,'notional'].median():,.0f} | losses {df.loc[l,'notional'].median():,.0f}")
    print(f"  median leverage  wins {df.loc[w,'lev'].median():.0f} | losses {df.loc[l,'lev'].median():.0f}")
    d = df.sort_values("opened").reset_index(drop=True)
    d["prev_loss"] = (d["pnl"].shift(1) < 0)
    if d["prev_loss"].sum() > 0:
        print(f"  median notional AFTER a loss {d.loc[d.prev_loss,'notional'].median():,.0f} "
              f"vs otherwise {d.loc[~d.prev_loss,'notional'].median():,.0f}")

    print(f"\n=== PROFIT CONCENTRATION ===")
    for k in [1, 5, 10, 20]:
        print(f"  top {k:>2} winners = {df.nlargest(k,'pnl')['pnl'].sum():8.2f} USDT "
              f"({df.nlargest(k,'pnl')['pnl'].sum()/df.loc[w,'pnl'].sum()*100:5.1f}% of gross profit)")

    print(f"\n=== MONTHLY ===")
    m = df.groupby(df["opened"].dt.to_period("M")).agg(trades=("pnl", "size"), pnl=("pnl", "sum"),
                                                       wins=("pnl", lambda s: (s > 0).sum()))
    m["win_rate"] = (m["wins"] / m["trades"] * 100).round(1)
    print(m.to_string())

    print(f"\n=== WHAT WE CANNOT TELL FROM A TRADE LOG ===")
    print("  - account equity / starting capital -> no % return, no % drawdown")
    print("  - OPEN positions at the snapshot -> the real risk may be sitting unrealised")
    print("  - the entry RULES -> outcomes are visible, decisions are not")
    print("  - the other ~thousands of trades before this 200-trade window")


if __name__ == "__main__":
    main()
