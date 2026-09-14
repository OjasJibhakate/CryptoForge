# ===========================================================================
# CRYPTOFORGE :: LEVEL 2 WHALE TRACKER
# ===========================================================================
import ccxt
import pandas as pd

# 🚨 PASTE YOUR DEMO TRADING KEYS HERE
API_KEY = "YOUR_API_KEY"
SECRET_KEY = "YOUR_SECRET_KEY"

exchange = ccxt.binance({
    'apiKey': API_KEY,
    'secret': SECRET_KEY,
    'enableRateLimit': True,
    'options': {'defaultType': 'future'}
})
# 🛡️ Lock to the Demo Network
exchange.enable_demo_trading(True)

def scan_order_book(symbol="BTC/USDT", depth=100):
    print(f"📡 Scanning Level 2 Order Book for {symbol} (Depth: {depth} levels)...")
    
    # Fetch the live limit orders currently sitting on the exchange
    order_book = exchange.fetch_order_book(symbol, limit=depth)
    
    # Extract Bids (Buyers) and Asks (Sellers)
    # Format: [Price, Quantity]
    bids = order_book['bids']
    asks = order_book['asks']
    
    # Create DataFrames for easier math
    df_bids = pd.DataFrame(bids, columns=['Price', 'BTC_Quantity'])
    df_asks = pd.DataFrame(asks, columns=['Price', 'BTC_Quantity'])
    
    # 1. Calculate Total Pressure
    total_bid_vol = df_bids['BTC_Quantity'].sum()
    total_ask_vol = df_asks['BTC_Quantity'].sum()
    
    # Imbalance Ratio: > 50% means Bulls are stronger, < 50% means Bears are stronger
    imbalance = (total_bid_vol / (total_bid_vol + total_ask_vol)) * 100

    print("\n========================================================")
    print("🐋 THE WHALE TRACKER: LIVE ORDER BOOK PRESSURE")
    print("========================================================")
    print(f"🟢 Total Bid Volume (Buyers) : {total_bid_vol:.2f} BTC")
    print(f"🔴 Total Ask Volume (Sellers): {total_ask_vol:.2f} BTC")
    
    if imbalance > 55:
        print(f"📈 MARKET IMBALANCE: {imbalance:.1f}% BULLISH (Strong Floor)")
    elif imbalance < 45:
        print(f"📉 MARKET IMBALANCE: {imbalance:.1f}% BEARISH (Heavy Ceiling)")
    else:
        print(f"⚖️ MARKET IMBALANCE: {imbalance:.1f}% NEUTRAL (Chop Zone)")

    # 2. Detect the Single Biggest Whale Walls
    print("\n🚨 DETECTING MASSIVE LIMIT ORDERS (WHALE WALLS):")
    
    # Find the single price level with the highest amount of Bitcoin sitting on it
    biggest_bid = df_bids.loc[df_bids['BTC_Quantity'].idxmax()]
    biggest_ask = df_asks.loc[df_asks['BTC_Quantity'].idxmax()]
    
    print(f"🛡️ Biggest BUY Wall  : {biggest_bid['BTC_Quantity']:.2f} BTC sitting at ${biggest_bid['Price']:.2f}")
    print(f"🧱 Biggest SELL Wall : {biggest_ask['BTC_Quantity']:.2f} BTC sitting at ${biggest_ask['Price']:.2f}")
    print("========================================================\n")

if __name__ == "__main__":
    try:
        scan_order_book('BTC/USDT', depth=100)
    except Exception as e:
        print(f"🚨 Radar Failure: {e}")