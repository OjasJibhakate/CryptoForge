# ===========================================================================
# CRYPTOFORGE MACRO :: 83-DAY TREND ENGINE WITH 3x ATR TRAILING ARMOR
# ===========================================================================
import time
import json
import os
import csv
import requests
import pandas as pd
import numpy as np
from datetime import datetime, timedelta, timezone

# =====================================================================
# ⚙️ MACRO PARAMETERS
# =====================================================================
TARGET_ASSETS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT"] # Keep macro strictly to large caps
LOOKBACK_N = 83                        # The verified parameter plateau
ATR_PERIOD = 14
ATR_MULTIPLIER = 3.0                   # 3x ATR Flash-Crash Armor

STATE_FILE = "macro_state.json"
CSV_FILE = "crypto_macro_trades.csv"

# =====================================================================
# 🧠 MEMORY BANK MANAGEMENT
# =====================================================================
def load_state():
    """Loads the trailing stops and active positions from the hard drive."""
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, "r") as f:
            state = json.load(f)
            
            # 🛡️ THE UPGRADE: If a new coin was added to the script, inject it into the memory bank safely
            for sym in TARGET_ASSETS:
                if sym not in state:
                    state[sym] = {"status": "FLAT", "entry_price": 0.0, "highest_price": 0.0, "trailing_stop": 0.0}
            return state
            
    # Default clean state for the very first run
    return {sym: {"status": "FLAT", "entry_price": 0.0, "highest_price": 0.0, "trailing_stop": 0.0} for sym in TARGET_ASSETS}

def save_state(state):
    """Saves active positions so the bot survives laptop reboots."""
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=4)

def log_macro_trade(symbol, trade_type, price, trigger, status):
    """Logs the macro executions to a dedicated CSV for analysis."""
    headers = ["timestamp", "symbol", "type", "price", "trigger", "status"]
    file_exists = os.path.exists(CSV_FILE)
    with open(CSV_FILE, mode="a", newline="") as f:
        writer = csv.writer(f)
        if not file_exists:
            writer.writerow(headers)
        writer.writerow([
            datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            symbol, trade_type, round(price, 2), trigger, status
        ])

# =====================================================================
# 📊 MARKET DATA & ATR MATH
# =====================================================================
def fetch_daily_klines(symbol, limit=100):
    """Fetches exactly enough daily data to calculate 83-day momentum and ATR."""
    try:
        url = f"https://fapi.binance.com/fapi/v1/klines?symbol={symbol.upper()}&interval=1d&limit={limit}"
        data = requests.get(url).json()
        cols = ['timestamp', 'open', 'high', 'low', 'close', 'volume', 
                'close_time', 'qav', 'num_trades', 'tbbav', 'tbqav', 'ignore']
        df = pd.DataFrame(data, columns=cols)
        
        for col in ['high', 'low', 'close']:
            df[col] = df[col].astype(float)
            
        return df
    except Exception as e:
        print(f"❌ API Error on {symbol}: {e}")
        return pd.DataFrame()

def calculate_macro_metrics(df):
    """Calculates the 83-day baseline and the dynamic 3x ATR."""
    # True Range Math
    df['prev_close'] = df['close'].shift(1)
    df['tr'] = df[['high', 'low', 'prev_close']].apply(
        lambda x: max(x['high'] - x['low'], abs(x['high'] - x['prev_close']), abs(x['low'] - x['prev_close'])), axis=1
    )
    # Average True Range (ATR)
    df['atr'] = df['tr'].rolling(window=ATR_PERIOD).mean()
    
    current_close = df['close'].iloc[-1]
    past_close = df['close'].iloc[-(LOOKBACK_N + 1)] # The close 83 days ago
    current_atr = df['atr'].iloc[-1]
    
    return current_close, past_close, current_atr

# =====================================================================
# 🛡️ THE DAILY RESOLVER
# =====================================================================
def execute_daily_scan():
    print(f"\n========================================================")
    print(f"🌍 [UTC 00:00] INITIATING CRYPTOFORGE MACRO SCAN...")
    print(f"========================================================")
    
    state = load_state()
    
    for symbol in TARGET_ASSETS:
        df = fetch_daily_klines(symbol)
        if df.empty or len(df) < LOOKBACK_N + 5:
            print(f"⚠️ Insufficient data for {symbol}. Skipping...")
            continue
            
        current_close, past_close, current_atr = calculate_macro_metrics(df)
        sym_state = state[symbol]
        
        print(f"📊 {symbol} | Price: ${current_close:,.2f} | 83-Day Base: ${past_close:,.2f} | ATR: ${current_atr:,.2f}")
        
        # --- 1. ENTRY LOGIC (Checking for a new macro uptrend) ---
        if sym_state["status"] == "FLAT":
            if current_close > past_close:
                print(f"   🚀 [MACRO BREAKOUT] {symbol} crossed 83-day baseline! Executing BUY.")
                
                sym_state["status"] = "LONG"
                sym_state["entry_price"] = current_close
                sym_state["highest_price"] = current_close
                sym_state["trailing_stop"] = current_close - (ATR_MULTIPLIER * current_atr)
                
                print(f"   🎯 Armor Engaged: 3x ATR Trailing Stop set at ${sym_state['trailing_stop']:,.2f}")
                log_macro_trade(symbol, "BUY", current_close, "83_DAY_CROSS", "OPEN")
            else:
                print(f"   📉 Trend Bearish. Remaining in CASH.")

        # --- 2. EXIT & TRAILING STOP LOGIC (Protecting Capital) ---
        elif sym_state["status"] == "LONG":
            # Update the highest price achieved during the trade
            if current_close > sym_state["highest_price"]:
                sym_state["highest_price"] = current_close
                
            # Recalculate trailing stop (It can only go UP, never down)
            new_trailing_stop = sym_state["highest_price"] - (ATR_MULTIPLIER * current_atr)
            if new_trailing_stop > sym_state["trailing_stop"]:
                sym_state["trailing_stop"] = new_trailing_stop
                
            print(f"   🛡️ Active Trade | Highest: ${sym_state['highest_price']:,.2f} | Stop: ${sym_state['trailing_stop']:,.2f}")

            # Check if the armor was hit OR the 83-day trend completely died
            if current_close < sym_state["trailing_stop"]:
                print(f"   🛑 [ATR STOP HIT] Flash crash armor triggered! Executing SELL.")
                profit_pct = ((current_close - sym_state["entry_price"]) / sym_state["entry_price"]) * 100
                print(f"   💸 Net Trade Result: {profit_pct:+.2f}%")
                
                log_macro_trade(symbol, "SELL", current_close, "ATR_STOP", "CLOSED")
                sym_state["status"] = "FLAT"
                
            elif current_close < past_close:
                print(f"   📉 [MACRO REVERSAL] 83-Day baseline lost. Executing SELL.")
                profit_pct = ((current_close - sym_state["entry_price"]) / sym_state["entry_price"]) * 100
                print(f"   💸 Net Trade Result: {profit_pct:+.2f}%")
                
                log_macro_trade(symbol, "SELL", current_close, "BASELINE_LOSS", "CLOSED")
                sym_state["status"] = "FLAT"

    # Save the updated trailing stops to the hard drive
    save_state(state)
    print(f"💾 Macro state securely saved to hard disk.\n")

# =====================================================================
# ⏳ THE CRON-SLEEP SCHEDULER
# =====================================================================
if __name__ == "__main__":
    print("🚀 BOOTING CRYPTOFORGE MACRO ENGINE...")
    print("🛡️ 83-Day Baseline | 3x ATR Armor")
    
    while True:
        # 1. Execute the scan immediately upon startup
        execute_daily_scan()
        
        # 2. Calculate exact seconds until the next 00:01 UTC
        now_utc = datetime.now(timezone.utc)
        next_run = now_utc.replace(hour=0, minute=1, second=0, microsecond=0)
        
        if now_utc >= next_run:
            next_run += timedelta(days=1)
            
        sleep_seconds = (next_run - now_utc).total_seconds()
        
        hours, remainder = divmod(sleep_seconds, 3600)
        minutes, seconds = divmod(remainder, 60)
        
        print(f"💤 Macro Engine sleeping. Next execution at UTC 00:01 (in {int(hours)}h {int(minutes)}m)...")
        
        # Sleep until the next daily candle closes
        time.sleep(sleep_seconds)