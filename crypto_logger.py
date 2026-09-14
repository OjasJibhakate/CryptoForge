# ===========================================================================
# CRYPTOFORGE :: CONTINUOUS ALPHA LOGGER
# ===========================================================================
import time
import os
from datetime import datetime
import pandas as pd
from cryptoforge_master import fetch_crypto_data
from cryptoforge_engine import calculate_crypto_features, get_live_imbalance

LOG_FILE = "crypto_alpha_master.csv"

print("🚀 Booting the CryptoForge Sentinel Logger...")
print(f"📁 Data will be saved locally to: {LOG_FILE}")
print("⏳ Waiting for the start of the next minute to capture the first row...")

while True:
    now = datetime.now()
    
    # Trigger exactly at 2 seconds past the minute to let the exchange close the candle
    if now.second == 2: 
        try:
            # 1. Grab candles & calculate mathematical features
            raw_candles = fetch_crypto_data('BTC/USDT', '1m', limit=65)
            crypto_features = calculate_crypto_features(raw_candles)
            matrix = raw_candles.join(crypto_features)
            
            # 2. Grab the live Level 2 Order Book pressure
            imbalance, big_bid, big_ask = get_live_imbalance('BTC/USDT', 100)
            
            # 3. Isolate the live row and inject the Whale data
            live_row = matrix.iloc[-1:].copy()
            live_row['ob_imbalance_%'] = imbalance
            live_row['buy_wall_price'] = big_bid['Price']
            live_row['buy_wall_qty'] = big_bid['Qty']
            live_row['sell_wall_price'] = big_ask['Price']
            live_row['sell_wall_qty'] = big_ask['Qty']
            
            # 4. Append to your proprietary CSV dataset
            header = not os.path.exists(LOG_FILE)
            live_row.to_csv(LOG_FILE, mode='a', header=header, index=False)
            
            print(f"✅ [{now.strftime('%H:%M:%S')}] Logged! Close: ${live_row['Close'].values[0]} | Z: {live_row['crypto_z_5'].values[0]:.2f} | Imbalance: {imbalance:.1f}%")
            
            # Sleep for 50 seconds so it doesn't trigger multiple times in the same minute
            time.sleep(50)
            
        except Exception as e:
            print(f"🚨 Logger Error: {e}")
            time.sleep(5) # Brief pause before retrying if API drops
    else:
        # Check the clock every half second
        time.sleep(0.5)