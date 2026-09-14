# ===========================================================================
# CRYPTOFORGE :: TESTNET API CONNECTION MODULE
# ===========================================================================
import os
import ccxt
import pandas as pd

print("🚀 Booting CryptoForge API Test...")

# 🔐 Credentials come from the environment. Never hardcode keys in a repo.
#   Windows:  set BINANCE_TESTNET_API_KEY=...  &  set BINANCE_TESTNET_SECRET_KEY=...
#   Unix:     export BINANCE_TESTNET_API_KEY=... ; export BINANCE_TESTNET_SECRET_KEY=...
API_KEY = os.environ.get("BINANCE_TESTNET_API_KEY", "")
SECRET_KEY = os.environ.get("BINANCE_TESTNET_SECRET_KEY", "")

# Initialize the Exchange (Configured for Futures)
exchange = ccxt.binance({
    'apiKey': API_KEY,
    'secret': SECRET_KEY,
    'enableRateLimit': True,
    'options': {
        'defaultType': 'future', # We are trading Perpetual Futures, not spot
    }
})

# 🛡️ THE FIREWALL: Forces the code to strictly use the Demo Trading network
exchange.enable_demo_trading(True) 

def fetch_crypto_data(symbol, timeframe, limit=5):
    print(f"📡 Fetching live {timeframe} candles for {symbol}...")
    # Fetch Open, High, Low, Close, Volume
    ohlcv = exchange.fetch_ohlcv(symbol, timeframe, limit=limit)
    
    df = pd.DataFrame(ohlcv, columns=['timestamp', 'Open', 'High', 'Low', 'Close', 'Volume'])
    # Convert crypto timestamp (milliseconds) to readable datetime
    df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
    return df

if __name__ == "__main__":
    try:
        # 1. Ping the server and check your Testnet wallet balance
        balance = exchange.fetch_balance()
        print(f"💰 Testnet USDT Balance: ${balance['USDT']['total']}")

        # 2. Fetch the latest 5 minutes of Bitcoin price action
        btc_data = fetch_crypto_data('BTC/USDT', '1m', 5)
        print("\n📊 Live BTC/USDT 1-Min Data:")
        print(btc_data[['timestamp', 'Close']])
        
    except Exception as e:
        print(f"🚨 API Connection Failed: {e}")