import os
import sys
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass
from copy_trader_analysis import parse, PATH

df = parse(PATH).dropna(subset=["pnl"]).reset_index(drop=True)
df = df[(df["size"] > 0) & (df["entry"] > 0)].copy()
df["notional"] = df["size"] * df["entry"]
df["implied_move_pct"] = df["pnl"] / df["notional"] * 100.0
df["direction"] = np.where(df["side"] == "Short", -1, 1)
# actual favourable/unfavourable price move
df["px_move_pct"] = (df["close"] - df["entry"]) / df["entry"] * 100.0

w = df["pnl"] > 0
l = df["pnl"] < 0

print(f"trades with usable size: {len(df)}")
print(f"\n=== IMPLIED PRICE MOVE PER TRADE (PnL / notional) ===")
print(f"wins   : median {df.loc[w,'implied_move_pct'].abs().median():.3f}%  "
      f"mean {df.loc[w,'implied_move_pct'].abs().mean():.3f}%  "
      f"p90 {df.loc[w,'implied_move_pct'].abs().quantile(.9):.3f}%")
if l.sum():
    print(f"losses : median {df.loc[l,'implied_move_pct'].abs().median():.3f}%  "
          f"mean {df.loc[l,'implied_move_pct'].abs().mean():.3f}%  "
          f"max {df.loc[l,'implied_move_pct'].abs().max():.3f}%")

print(f"\n=== REALISED PRICE MOVE, entry -> exit ===")
print(f"wins   : median {df.loc[w,'px_move_pct'].abs().median():.3f}%   "
      f"(in their favour: {(np.sign(df.loc[w,'px_move_pct'])==df.loc[w,'direction']).mean()*100:.0f}%)")
if l.sum():
    print(f"losses : median {df.loc[l,'px_move_pct'].abs().median():.3f}%")

print(f"\n=== NOTIONAL CONCENTRATION ===")
print(f"notional: median {df['notional'].median():,.0f} | mean {df['notional'].mean():,.0f} | "
      f"max {df['notional'].max():,.0f} | sum {df['notional'].sum():,.0f}")
print(f"top 5 trades by notional = {df.nlargest(5,'notional')['notional'].sum()/df['notional'].sum()*100:.1f}% of all notional")
print(f"\nlargest notional trade:")
r = df.nlargest(1, "notional").iloc[0]
print(f"  {r['symbol']} {r['side']} {r['lev']}x notional {r['notional']:,.0f} pnl {r['pnl']:+,.2f} "
      f"move {r['px_move_pct']:+.2f}% hold {r['hold_s']:.0f}s")

print(f"\n=== NOTE ON DATA QUALITY ===")
print("'Max. Open Interest' is the PEAK size, not necessarily the size at close.")
print("Sizes change when the trader adds/reduces, so implied moves are approximate.")
