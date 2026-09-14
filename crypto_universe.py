# ===========================================================================
# CRYPTOFORGE :: DUAL-TIER UNIVERSE SELECTION (Research-Optimized)
# ===========================================================================
import requests
import pandas as pd

def generate_dynamic_universe(max_altcoins=4, min_volume_usd=250000000, min_vol=0.05, max_vol=0.15):
    print("🔄 Initializing Dual-Tier Universe Sweep...")
    core_universe = ['BTCUSDT', 'ETHUSDT']
    
    try:
        url = "https://fapi.binance.com/fapi/v1/ticker/24hr"
        response = requests.get(url, timeout=10).json()
        
        altcoin_pool = []
        
        for ticker in response:
            symbol = ticker['symbol']
            
            if not symbol.endswith('USDT') or symbol in core_universe or "_" in symbol:
                continue
                
            volume_usd = float(ticker['quoteVolume'])
            high_price = float(ticker['highPrice'])
            low_price = float(ticker['lowPrice'])
            close_price = float(ticker['lastPrice'])
            
            # Calculate daily kinetic range (Volatility)
            daily_volatility = (high_price - low_price) / close_price if close_price > 0 else 0
            
            # 🎯 THE SWEET SPOT FILTER: Volume > $250M AND Volatility between 5% and 15%
            if volume_usd >= min_volume_usd and (min_vol <= daily_volatility <= max_vol):
                altcoin_pool.append({
                    'symbol': symbol,
                    'volume': volume_usd,
                    'volatility': daily_volatility
                })
        
        df_alts = pd.DataFrame(altcoin_pool)
        if not df_alts.empty:
            # Sort by highest volume first to ensure maximum liquidity
            df_alts = df_alts.sort_values(by='volume', ascending=False)
            top_satellites = df_alts['symbol'].head(max_altcoins).tolist()
        else:
            top_satellites = ['SOLUSDT', '1000PEPEUSDT', 'HYPEUSDT', 'SPCXUSDT'] 
            
        final_trading_universe = core_universe + top_satellites
        
        print("\n========================================================")
        print("⚡️ DUAL-TIER MATRIX: OPTIMIZED SWEET SPOTS ENGAGED")
        print("========================================================")
        print(f"🔒 TIER 1 CORE (Locked)       : {core_universe}")
        print(f"🔥 TIER 2 SATELLITES (Dynamic): {top_satellites}")
        print(f"🎯 SYSTEM TARGET UNIVERSE    : {final_trading_universe}")
        print("========================================================\n")
        
        return final_trading_universe

    except Exception as e:
        print(f"🚨 Universe sweep failed ({e}).")
        return ['BTCUSDT', 'ETHUSDT', 'SOLUSDT', '1000PEPEUSDT', 'HYPEUSDT', 'SPCXUSDT']

if __name__ == "__main__":
    # Test the module live to see which coins pass the Sweet Spot test today
    TARGET_SYMBOLS = generate_dynamic_universe()