import pandas as pd
import numpy as np
import requests
import matplotlib.pyplot as plt
from datetime import datetime

# =====================================================================
# ⚙️ SYSTEM PARAMETERS & COST MODEL
# =====================================================================
SYMBOL = "BTCUSDT"
TIMEFRAME = "1d"
LOOKBACK_N = 83           # The 'N-Day' Momentum Window
FEE_RATE = 0.0010         # 0.10% Binance Taker Fee (Round trip = 0.20%)

print(f"🚀 Booting CryptoForge Trend Backtest Engine...")
print(f"📡 Fetching historical daily data for {SYMBOL}...")

# =====================================================================
# 📂 1. DATA INGESTION (Binance REST API)
# =====================================================================
def fetch_historical_daily_data(symbol):
    """Fetches a locked, static timeframe to prevent shape-shifting backtest results."""
    # Freeze the timeline: Jan 1, 2024 to June 1, 2026
    start_ts = int(datetime(2024, 1, 1).timestamp() * 1000)
    end_ts = int(datetime(2026, 6, 1).timestamp() * 1000)
    
    url = f"https://fapi.binance.com/fapi/v1/klines?symbol={symbol.upper()}&interval={TIMEFRAME}&startTime={start_ts}&endTime={end_ts}&limit=1000"
    data = requests.get(url).json()
    
    # Safety Check: Did Binance give us the data?
    if not data or len(data) < 100:
        print(f"❌ ERROR: Binance API returned insufficient data. Check connection or dates.")
        return pd.DataFrame()
        
    cols = ['timestamp', 'open', 'high', 'low', 'close', 'volume', 
            'close_time', 'qav', 'num_trades', 'tbbav', 'tbqav', 'ignore']
    df = pd.DataFrame(data, columns=cols)
    
    df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
    for col in ['open', 'high', 'low', 'close', 'volume']:
        df[col] = df[col].astype(float)
        
    return df.set_index('timestamp')

# Update the call to remove the limit parameter:
df = fetch_historical_daily_data(SYMBOL)

# =====================================================================
# 🧠 2. SIGNAL GENERATION (Time-Series Momentum)
# =====================================================================
# Hypothesis: If today's close is higher than the close N days ago, the trend is UP.
df['momentum_baseline'] = df['close'].shift(LOOKBACK_N)

# 1 = Long (Bullish), 0 = Cash/Flat (Bearish)
# We use np.where to strictly define the logic.
df['signal'] = np.where(df['close'] > df['momentum_baseline'], 1, 0)

# =====================================================================
# 🛡️ 3. VECTORIZED EXECUTION & COST MODEL (The Truth Machine)
# =====================================================================
# CRITICAL: We shift the signal by 1. 
# If the signal fires at 23:59 tonight, we can only execute at tomorrow's open.
# Without this shift, you are predicting the past (Lookahead Bias).
df['position'] = df['signal'].shift(1)

# Calculate standard daily market returns
df['market_return'] = df['close'].pct_change()

# Calculate Strategy Returns (Market Return * Our Position)
df['strategy_return'] = df['position'] * df['market_return']

# 💸 Apply Trading Costs
# We only pay fees when our position CHANGES (e.g., going from 0 to 1, or 1 to 0)
df['trade_happened'] = df['position'].diff().abs()
df['strategy_return'] = np.where(
    df['trade_happened'] == 1, 
    df['strategy_return'] - FEE_RATE, 
    df['strategy_return']
)

# Drop NaNs caused by lookback periods
df = df.dropna()

# =====================================================================
# 🧮 4. PERFORMANCE METRICS (The Tear Sheet)
# =====================================================================
# Calculate compounding equity curves
df['cum_market'] = (1 + df['market_return']).cumprod()
df['cum_strategy'] = (1 + df['strategy_return']).cumprod()

# Core Metrics
total_trades = df['trade_happened'].sum()
strategy_net = (df['cum_strategy'].iloc[-1] - 1) * 100
market_net = (df['cum_market'].iloc[-1] - 1) * 100

# Annualized Volatility & Sharpe Ratio (assuming risk-free rate = 0)
trading_days = 365
strat_volatility = df['strategy_return'].std() * np.sqrt(trading_days)
sharpe_ratio = (df['strategy_return'].mean() * trading_days) / strat_volatility if strat_volatility != 0 else 0

# Max Drawdown Calculation
df['peak'] = df['cum_strategy'].cummax()
df['drawdown'] = (df['cum_strategy'] - df['peak']) / df['peak']
max_drawdown = df['drawdown'].min() * 100

print("\n" + "="*50)
print("📊 MACRO TREND BACKTEST RESULTS")
print("="*50)
print(f"Asset Tested:      {SYMBOL}")
print(f"Lookback Window:   {LOOKBACK_N} Days")
print(f"Total Trades:      {int(total_trades)} Executions")
print("-" * 50)
print(f"Buy & Hold Return: {market_net:.2f}%")
print(f"Strategy Return:   {strategy_net:.2f}%")
print(f"Max Drawdown:      {max_drawdown:.2f}%")
print(f"Sharpe Ratio:      {sharpe_ratio:.2f}")
print("="*50 + "\n")

# =====================================================================
# 📈 5. VISUALIZATION
# =====================================================================
plt.figure(figsize=(12, 6))
plt.plot(df.index, df['cum_market'], label='Buy & Hold (Market)', color='gray', alpha=0.6)
plt.plot(df.index, df['cum_strategy'], label=f'{LOOKBACK_N}-Day Momentum Strategy', color='cyan', linewidth=2)

# Highlight active trade zones (Green background when in the market)
plt.fill_between(df.index, df['cum_strategy'].min(), df['cum_strategy'].max(), 
                 where=df['position']==1, color='green', alpha=0.1, label='In Market')

plt.title(f"Macro Trend Engine: {SYMBOL} ({LOOKBACK_N}-Day Momentum)")
plt.ylabel("Compounded Capital (Multiplier)")
plt.legend()
plt.grid(True, alpha=0.2)
plt.style.use('dark_background')
plt.show()