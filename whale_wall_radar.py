# ===========================================================================
# CRYPTOFORGE :: LIVE WHALE WALL RADAR (Level 2 WebSocket)
# ===========================================================================
import websocket
import json

# Target the exact coin you want to track (Lower case for WebSockets)
SYMBOL = "btcusdt"
WS_URL = f"wss://fstream.binance.com/ws/{SYMBOL}@depth@100ms"

# 🚨 Set the Whale Alarm Threshold: $2 Million USD
WHALE_THRESHOLD_USD = 2000000 

def on_message(ws, message):
    data = json.loads(message)
    
    # 'b' = Bids (Buyers / Floors) | 'a' = Asks (Sellers / Ceilings)
    bids = data.get('b', [])
    asks = data.get('a', [])
    
    # Check the Ask (Sell) side for massive Resistance Walls
    for ask in asks:
        price = float(ask[0])
        qty = float(ask[1])
        usd_value = price * qty
        
        if usd_value >= WHALE_THRESHOLD_USD:
            print(f"\n🚨 [BEAR WHALE DETECTED] 🧱 SELL WALL: ${usd_value:,.0f} sitting at Price: ${price:,.2f}")
            
    # Check the Bid (Buy) side for massive Support Floors
    for bid in bids:
        price = float(bid[0])
        qty = float(bid[1])
        usd_value = price * qty
        
        if usd_value >= WHALE_THRESHOLD_USD:
            print(f"\n🟢 [BULL WHALE DETECTED] 🛡️ BUY FLOOR: ${usd_value:,.0f} sitting at Price: ${price:,.2f}")

def on_error(ws, error):
    print(f"Connection Error: {error}")

def on_close(ws, close_status_code, close_msg):
    print("Whale Radar Disconnected.")

def on_open(ws):
    print("========================================================")
    print(f"📡 WHALE RADAR ONLINE: Scanning {SYMBOL.upper()} Order Book every 100ms")
    print(f"🎯 Alert Threshold: ${WHALE_THRESHOLD_USD:,.0f}")
    print("========================================================")

if __name__ == "__main__":
    # You must pip install websocket-client if you haven't already
    ws = websocket.WebSocketApp(WS_URL,
                              on_open=on_open,
                              on_message=on_message,
                              on_error=on_error,
                              on_close=on_close)
    ws.run_forever()