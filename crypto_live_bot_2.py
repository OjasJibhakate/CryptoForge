# ===========================================================================
# CRYPTOFORGE :: AUTONOMOUS MULTI-ASSET LIVE TRADING CORE (V2: MACRO TARGETS)
# ===========================================================================
import json
import time
import pickle
import os
import csv
import requests
import websocket
import pandas as pd
import numpy as np
from datetime import datetime

# Import custom quantitative modules
from crypto_universe import generate_dynamic_universe
from crypto_metabrain import engineer_institutional_features

# =====================================================================
# ⚙️ SYSTEM STATE & CONFIGURATION MATRIX
# =====================================================================
MODEL_FILE = "meta_brain_lgb.pkl"
CSV_FILE = "crypto_live_trades_2.csv"     # 📝 NEW CSV FILE

AI_CONFIDENCE_THRESHOLD = 0.70    
WHALE_WALL_USD = 2000000          
PROFIT_TARGET_PCT = 0.0200        # 🎯 UPGRADED: 2.0% Target
STOP_LOSS_PCT = 0.0100            # 🛡️ UPGRADED: 1.0% Stop Loss

# Global Persistent Registries
MARKET_MEMORY = {}
ACTIVE_POSITIONS = {}             
START_TIME = time.time()
MODEL_PAYLOAD = None

# =====================================================================
# 📝 STABLE CSV LOGGING ENGINE
# =====================================================================
def log_live_trade(symbol, trade_type, price, probability, target, stop, status="OPEN"):
    headers = ["timestamp", "symbol", "type", "price", "probability", "target", "stop", "status"]
    file_exists = os.path.exists(CSV_FILE)
    with open(CSV_FILE, mode="a", newline="") as f:
        writer = csv.writer(f)
        if not file_exists:
            writer.writerow(headers)
        writer.writerow([
            datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            symbol, trade_type, price, probability, target, stop, status
        ])

# =====================================================================
# 🧊 HISTORICAL PRIMING (COLD START)
# =====================================================================
def get_historical_klines(symbol, limit=80):
    try:
        url = f"https://fapi.binance.com/fapi/v1/klines?symbol={symbol.upper()}&interval=1m&limit={limit}"
        data = requests.get(url).json()
        cols = ['timestamp', 'open', 'high', 'low', 'close', 'volume', 
                'close_time', 'qav', 'num_trades', 'tbbav', 'tbqav', 'ignore']
        df = pd.DataFrame(data, columns=cols)
        for col in cols:
            if col not in ['ignore']:
                df[col] = pd.to_numeric(df[col], errors='coerce')
        return df
    except Exception as e:
        print(f"❌ Error fetching history for {symbol}: {e}")
        return pd.DataFrame()

# =====================================================================
# 🐋 THE WHALE RADAR VETO CHECK
# =====================================================================
def check_whale_veto(symbol, current_price):
    try:
        url = f"https://fapi.binance.com/fapi/v1/depth?symbol={symbol.upper()}&limit=50"
        ob = requests.get(url).json()
        target_price = current_price * (1 + PROFIT_TARGET_PCT)
        for ask in ob['asks']:
            price = float(ask[0])
            usd_value = price * float(ask[1])
            if price <= target_price and usd_value >= WHALE_WALL_USD:
                print(f"   🛑 [WHALE VETO] ${usd_value:,.0f} SELL WALL detected at ${price:,.2f}!")
                return True
        return False
    except:
        return False

# =====================================================================
# 🧠 THE LIVE PREDICTION CORE & SIGNAL RESOLVER (MATRIX PATCHED)
# =====================================================================
def process_live_prediction(symbol, event_data):
    global MARKET_MEMORY, MODEL_PAYLOAD, ACTIVE_POSITIONS
    
    symbol = symbol.upper()
    
    try:
        kline = event_data["k"]
        close_price = float(kline["c"])
        high_price = float(kline["h"])
        low_price = float(kline["l"])
        
        # --- 1. STRICT POSITION RESOLVER ---
        if symbol in ACTIVE_POSITIONS:
            pos = ACTIVE_POSITIONS[symbol]
            if high_price >= pos["target"]:
                print(f"🎉 [TARGET HIT] {symbol} hit profit target at ${pos['target']:,.4f}!")
                log_live_trade(symbol, "SELL", pos["target"], pos["prob"], pos["target"], pos["stop"], "WIN")
                del ACTIVE_POSITIONS[symbol]
            elif low_price <= pos["stop"]:
                print(f"🛡️ [STOP LOSS TRIGGERED] {symbol} cut at loss floor ${pos['stop']:,.4f}!")
                log_live_trade(symbol, "SELL", pos["stop"], pos["prob"], pos["target"], pos["stop"], "LOSS")
                del ACTIVE_POSITIONS[symbol]
        
        # --- 2. UPDATE CONTINUOUS MEMORY & AUTOMATIC SELF-HEALING ---
        new_row = pd.DataFrame([{
            "timestamp": int(kline["t"]),
            "open": float(kline["o"]),
            "high": high_price,
            "low": low_price,
            "close": close_price,
            "volume": float(kline["v"]),
            "close_time": int(kline.get("T", kline["t"] + 59999)), # 🛡️ PATCH 1: The Missing Link Fixed
            "qav": float(kline["q"]),
            "num_trades": int(kline["n"]),
            "tbbav": float(kline["V"]),
            "tbqav": float(kline["Q"]),
            "ignore": 0
        }])
        
        if symbol not in MARKET_MEMORY or MARKET_MEMORY[symbol].empty:
            MARKET_MEMORY[symbol] = get_historical_klines(symbol)
            
        MARKET_MEMORY[symbol] = pd.concat([MARKET_MEMORY[symbol], new_row]).iloc[-100:].reset_index(drop=True)
        
        if "ETHUSDT" not in MARKET_MEMORY or len(MARKET_MEMORY["ETHUSDT"]) < 65:
            print("🔄 [SELF-HEALING] ETHUSDT baseline data starved. Re-fetching...")
            MARKET_MEMORY["ETHUSDT"] = get_historical_klines("ETHUSDT")
            
        if "BTCUSDT" not in MARKET_MEMORY or len(MARKET_MEMORY["BTCUSDT"]) < 65:
            print("🔄 [SELF-HEALING] BTCUSDT baseline data starved. Re-fetching...")
            MARKET_MEMORY["BTCUSDT"] = get_historical_klines("BTCUSDT")

        if len(MARKET_MEMORY[symbol]) < 65:
            print(f"⚠️ [SCAN ABORTED] {symbol} memory buffer too shallow ({len(MARKET_MEMORY[symbol])}/65 rows).")
            return
            
        eth_df = MARKET_MEMORY["ETHUSDT"].copy()
        target_df = MARKET_MEMORY[symbol].copy()
        
        target_df = engineer_institutional_features(target_df)
        eth_df = eth_df[['timestamp', 'close', 'volume']].copy()
        eth_df.columns = ['timestamp', 'eth_close', 'eth_volume']
        
        target_df['timestamp'] = target_df['timestamp'].astype(float).astype(np.int64)
        eth_df['timestamp'] = eth_df['timestamp'].astype(float).astype(np.int64)
        
        merged_live = pd.merge(target_df, eth_df, on='timestamp', how='left')
        merged_live = merged_live.ffill().bfill() 
        
        merged_live['eth_btc_ratio'] = merged_live['eth_close'] / (MARKET_MEMORY["BTCUSDT"]['close'].iloc[-1] + 1e-8)
        merged_live['eth_return_5m'] = np.log(merged_live['eth_close'] / merged_live['eth_close'].shift(5))
        merged_live['btc_eth_momentum_diff'] = merged_live['return_5m'] - merged_live['eth_return_5m']
        
        # 🛡️ PATCH 2: Target-Specific DropNA
        feature_cols = [
            'return_1m', 'return_5m', 'volatility_15m', 'volatility_60m',
            'volume_z_15m', 'volume_z_60m', 'pv_momentum',
            'distance_from_high', 'distance_from_low', 'rsi_approx',
            'whale_buy_pressure', 'whale_pressure_surge',
            'eth_btc_ratio', 'eth_return_5m', 'btc_eth_momentum_diff'
        ]
        
        final_vector_df = merged_live.dropna(subset=feature_cols).reset_index(drop=True)
        
        if final_vector_df.empty:
            nan_cols = merged_live[feature_cols].columns[merged_live[feature_cols].isna().any()].tolist()
            print(f"⚠️ [SCAN ABORTED] Matrix for {symbol} went empty after dropna().")
            print(f"   ↳ Broken AI Feature Columns: {nan_cols}")
            return
            
        latest_candle_features = final_vector_df.iloc[-1]
        X_live = latest_candle_features[feature_cols].values.reshape(1, -1)
        probability = MODEL_PAYLOAD["model"].predict(X_live)[0]
        
        print(f"🔮 [AI SCAN] {symbol:<10} | Close: ${close_price:,.4f} | Prob: {probability*100:6.2f}%")
        
        # --- 3. ORDER PLACEMENT ---
        if probability >= AI_CONFIDENCE_THRESHOLD and symbol not in ACTIVE_POSITIONS:
            print("\n" + "="*50)
            print(f"🚨 [AI BUY SIGNAL DETECTED] {symbol} at ${close_price:,.4f}")
            
            if check_whale_veto(symbol, close_price):
                print("   ❌ TRADE ABORTED: Institutional manipulation block detected.")
            else:
                target_p = close_price * (1 + PROFIT_TARGET_PCT)
                stop_p = close_price * (1 - STOP_LOSS_PCT)
                
                print("   🟢 AIRSPACE CLEAR: EXECUTING PAPER TRADE BUY ORDER!")
                print(f"   🎯 Target: ${target_p:,.4f} | Stop: ${stop_p:,.4f}")
                
                ACTIVE_POSITIONS[symbol] = {
                    "target": target_p,
                    "stop": stop_p,
                    "prob": round(probability, 4),
                    "entry": close_price
                }
                log_live_trade(symbol, "BUY", close_price, round(probability, 4), round(target_p, 4), round(stop_p, 4), "OPEN")
            print("="*50 + "\n")
            
    except Exception as e:
        print(f"❌ [CRITICAL ENGINE ERROR on {symbol}]: {e}")
# =====================================================================
# 📡 STREAM CONNECTION ROUTING
# =====================================================================
def on_message(ws, message):
    global START_TIME
    try:
        if time.time() - START_TIME >= 86400:
            print("\n⏳ [24-HOUR RESET] Triggering memory flush...")
            ws.close()
            return

        payload = json.loads(message)
        event_data = payload.get("data", payload)
            
        if event_data.get("e") != "kline":
            return
            
        kline = event_data["k"]
        symbol = event_data["s"]
        
        if kline["x"]:
            print(f"\n⚡ [CANDLE CLOSE] {symbol} locked in.")
            process_live_prediction(symbol, event_data)
            
    except Exception as e:
        print(f"❌ [CRITICAL ENGINE ERROR on {symbol}]: {e}")

def on_error(ws, error):
    print(f"🚨 Connection Error Encountered: {error}")

def on_close(ws, close_status_code, close_msg):
    print("📡 Disconnected from Binance Market Matrix.")

def on_open(ws):
    print("\n📡 Connection Established. Streaming Live 2026 Institutional Data...")

if __name__ == "__main__":
    print("\n========================================================")
    print("🚀 BOOTING CRYPTOFORGE V2 (MACRO TARGETS ENGINE)...")
    print("========================================================")

    try:
        with open(MODEL_FILE, "rb") as f:
            MODEL_PAYLOAD = pickle.load(f)
        print("🧠 [SUCCESS] Meta-Brain Model loaded perfectly.")
    except Exception as e:
        print(f"❌ [FATAL] Core file `{MODEL_FILE}` could not be retrieved: {e}")
        exit()

    while True:
        START_TIME = time.time()
        
        print("🔭 Scanning live market for optimal velocity targets...")
        TARGET_SYMBOLS = generate_dynamic_universe(max_altcoins=4)
        WS_SYMBOLS = [s.lower() for s in TARGET_SYMBOLS]
        
        print("🧊 Initiating Cold Start...")
        MARKET_MEMORY.clear()
        for sym in TARGET_SYMBOLS:
            MARKET_MEMORY[sym] = get_historical_klines(sym)
            print(f"   ↳ primed {sym}: {len(MARKET_MEMORY[sym])} rows verified.")

        stream_params = "/".join([f"{s}@kline_1m" for s in WS_SYMBOLS])
        ws_url = f"wss://fstream.binance.com/market/stream?streams={stream_params}"
        
        ws = websocket.WebSocketApp(ws_url, on_open=on_open, on_message=on_message, on_error=on_error, on_close=on_close)
        ws.run_forever()
        
        print("🔄 Preparing to recycle socket loop pipelines in 5 seconds...")
        time.sleep(5)