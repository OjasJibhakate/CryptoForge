# ===========================================================================
# CRYPTOFORGE :: THE ALPHA ENGINE (Candles + Order Book Fusion)
# ===========================================================================
import numpy as np
import pandas as pd
from cryptoforge_master import fetch_crypto_data, exchange

def calculate_crypto_features(df):
    o, h, l, c = df["Open"], df["High"], df["Low"], df["Close"]
    f = pd.DataFrame(index=df.index)

    # Multi-horizon momentum z-scores 
    logc = np.log(c)
    for k, w in [(5, 20), (15, 40)]: 
        r = logc.diff(k)
        r_std = r.rolling(w, min_periods=5).std().replace(0.0, 1e-8)
        f[f"crypto_z_{k}"] = (r - r.rolling(w, min_periods=5).mean()) / r_std

    # Position in rolling range
    for n in (20, 60):
        hh, ll = h.rolling(n).max(), l.rolling(n).min()
        f[f"range_pos_{n}"] = (c - ll) / (hh - ll).replace(0.0, 1e-8)

    return f.ffill().bfill()

def get_live_imbalance(symbol="BTC/USDT", depth=100):
    # Fetch the live limit orders sitting on the exchange right now
    order_book = exchange.fetch_order_book(symbol, limit=depth)
    
    df_bids = pd.DataFrame(order_book['bids'], columns=['Price', 'Qty'])
    df_asks = pd.DataFrame(order_book['asks'], columns=['Price', 'Qty'])
    
    total_bid = df_bids['Qty'].sum()
    total_ask = df_asks['Qty'].sum()
    
    # Calculate the Bullish/Bearish Imbalance
    imbalance = (total_bid / (total_bid + total_ask)) * 100
    
    # Locate the massive Whale Walls
    biggest_bid = df_bids.loc[df_bids['Qty'].idxmax()]
    biggest_ask = df_asks.loc[df_asks['Qty'].idxmax()]
    
    return imbalance, biggest_bid, biggest_ask

if __name__ == "__main__":
    print("📡 Fetching the matrix: Live Candles + Order Book...")
    
    # 1. Grab the historical candles
    raw_candles = fetch_crypto_data('BTC/USDT', '1m', limit=65)
    
    # 2. Calculate the technical Z-scores and ranges
    crypto_features = calculate_crypto_features(raw_candles)
    final_matrix = raw_candles.join(crypto_features)
    
    # 3. Grab the LIVE Order Book snapshot
    imbalance, big_bid, big_ask = get_live_imbalance('BTC/USDT', 100)
    
    # 4. Inject the Whale Imbalance into the VERY LAST ROW (The live minute)
    final_matrix['ob_imbalance_%'] = np.nan # Fill past minutes with NaN
    final_matrix.loc[final_matrix.index[-1], 'ob_imbalance_%'] = imbalance
    
    print("\n========================================================")
    print("🔥 CRYPTOFORGE ALPHA MATRIX: LIVE SNAPSHOT")
    print("========================================================")
    
    # Print the last 3 minutes of data to see the fusion
    cols_to_show = ['timestamp', 'Close', 'crypto_z_5', 'ob_imbalance_%']
    print(final_matrix[cols_to_show].tail(3).to_string())
    
    print("\n🐋 CURRENT WHALE WALLS:")
    print(f"🛡️ BUY Floor   : {big_bid['Qty']:.2f} BTC @ ${big_bid['Price']:.2f}")
    print(f"🧱 SELL Ceiling: {big_ask['Qty']:.2f} BTC @ ${big_ask['Price']:.2f}")
    print("========================================================")