import pandas as pd
import numpy as np
import lightgbm as lgb
import pickle

# =====================================================================
# ⚙️ STEP 1: YOUR ORIGINAL INSTITUTIONAL FEATURE ENGINE
# =====================================================================
def engineer_institutional_features(df):
    # Force lowercase column names just in case
    df.columns = df.columns.str.lower()
    
    # Core math indicators
    df['return_1m'] = np.log(df['close'] / df['close'].shift(1))
    df['return_5m'] = np.log(df['close'] / df['close'].shift(5))
    
    df['volatility_15m'] = df['return_1m'].rolling(15).std()
    df['volatility_60m'] = df['return_1m'].rolling(60).std()
    
    df['volume_ma_15'] = df['volume'].rolling(15).mean()
    df['volume_z_15m'] = (df['volume'] - df['volume_ma_15']) / (df['volume'].rolling(15).std() + 1e-8)
    df['volume_ma_60'] = df['volume'].rolling(60).mean()
    df['volume_z_60m'] = (df['volume'] - df['volume_ma_60']) / (df['volume'].rolling(60).std() + 1e-8)
    
    df['pv_momentum'] = df['return_1m'] * df['volume']
    
    df['roll_high_60'] = df['high'].rolling(60).max()
    df['roll_low_60'] = df['low'].rolling(60).min()
    df['distance_from_high'] = (df['roll_high_60'] - df['close']) / df['close']
    df['distance_from_low'] = (df['close'] - df['roll_low_60']) / df['close']
    
    df['price_change_14'] = df['close'] - df['close'].shift(14)
    df['rsi_approx'] = df['price_change_14'].rolling(14).apply(lambda x: np.sum(x[x > 0]) / (np.sum(np.abs(x)) + 1e-8), raw=True)
    
    # 🐋 Whale Aggression Metrics
    df['whale_buy_pressure'] = df['tbqav'] / (df['qav'] + 1e-8)
    df['whale_pressure_surge'] = df['whale_buy_pressure'] / (df['whale_buy_pressure'].rolling(15).mean() + 1e-8)
    
    return df

# =====================================================================
# 🌐 STEP 2: PASTE THE NEW ETHER INTER-MARKET ENGINE HERE
# =====================================================================
def add_intermarket_ether_features(btc_df, eth_df):
    print("🌐 Engineering Ethereum Inter-Market Alpha Array...")
    
    # Force lowercase on Ethereum data to ensure match
    eth_df.columns = eth_df.columns.str.lower()
    
    # Extract only what we need to prevent memory bloat
    eth_df = eth_df[['timestamp', 'close', 'volume']].copy()
    eth_df.columns = ['timestamp', 'eth_close', 'eth_volume']
    
    # Merge both datasets on the exact millisecond timestamp row
    merged = pd.merge(btc_df, eth_df, on='timestamp', how='inner')
    
    # 1. ETH/BTC Price Ratio (Systemic outperformance tracking)
    merged['eth_btc_ratio'] = merged['eth_close'] / merged['close']
    
    # 2. ETH Momentum Vector
    merged['eth_return_5m'] = np.log(merged['eth_close'] / merged['eth_close'].shift(5))
    
    # 3. Spread Divergence (Are they breaking out together, or is one lagging?)
    merged['btc_eth_momentum_diff'] = merged['return_5m'] - merged['eth_return_5m']
    
    return merged

# =====================================================================
# 🎯 STEP 3: CREATE TARGET LABELS
# =====================================================================
def create_future_labels(df, horizon=15, target_pct=0.005):
    print(f"🎯 Creating Future Labels (Horizon: {horizon}m, Target: {target_pct*100}%)...")
    df['future_max'] = df['high'].shift(-horizon).rolling(horizon).max()
    df['target'] = (df['future_max'] >= df['close'] * (1 + target_pct)).astype(int)
    return df

# =====================================================================
# 🧠 STEP 4: RETRAIN THE COMPLETE MASTER PIPELINE
# =====================================================================
def main():
    btc_path = "Crypto_Historical_Vault/BTCUSDT_MASTER_1M.csv"
    eth_path = "Crypto_Historical_Vault/ETHUSDT_MASTER_1M.csv"
    
    print(f"📂 Loading Master Vault: {btc_path}")
    btc_df = pd.read_csv(btc_path)
    btc_df.columns = btc_df.columns.str.lower()
    
    print(f"📂 Loading Inter-Market Vault: {eth_path}")
    try:
        eth_df = pd.read_csv(eth_path)
    except FileNotFoundError:
        print(f"❌ [ERROR] Could not find {eth_path}! Please verify the file is in the vault folder.")
        return
    
    # Execute Feature Engineering Pipelines
    btc_df = engineer_institutional_features(btc_df)
    df = add_intermarket_ether_features(btc_df, eth_df)
    df = create_future_labels(df)
    
    # Drop rows that don't have historical rolling averages populated yet
    df = df.dropna().reset_index(drop=True)
    
    # ⚔️ EXPANDED FEATURE COLUMNS
    feature_cols = [
        'return_1m', 'return_5m', 'volatility_15m', 'volatility_60m',
        'volume_z_15m', 'volume_z_60m', 'pv_momentum',
        'distance_from_high', 'distance_from_low', 'rsi_approx',
        'whale_buy_pressure', 'whale_pressure_surge',
        'eth_btc_ratio', 'eth_return_5m', 'btc_eth_momentum_diff' # 🌐 NEW ETH FEATURES
    ]
    
    # Split training and testing sets chronologically
    split_idx = int(len(df) * 0.8)
    train_df = df.iloc[:split_idx]
    test_df = df.iloc[split_idx:]
    
    X_train = train_df[feature_cols].values
    y_train = train_df['target'].values
    X_test = test_df[feature_cols].values
    y_test = test_df['target'].values
    
    print(f"\n🧱 Data Split Verification Matrix:")
    print(f"   ↳ Training Set Size: {X_train.shape[0]} rows")
    print(f"   ↳ Out-of-Sample Test Size: {X_test.shape[0]} rows")
    
    print("\n🧠 Training Inter-Market LightGBM Crypto Matrix...")
    train_data = lgb.Dataset(X_train, label=y_train)
    
    params = {
        'objective': 'binary',
        'metric': 'binary_logloss',
        'boosting_type': 'gbdt',
        'learning_rate': 0.05,
        'num_leaves': 31,
        'is_unbalance': True,
        'verbose': -1
    }
    
    model = lgb.train(params, train_data, num_boost_round=100)
    
    print("\n🔮 Generating Raw Probability Arrays...")
    preds = model.predict(X_test)
    
    print("\n========================================================")
    print("🎯 QUANTITATIVE THRESHOLD SCANNER MATRIX")
    print("========================================================")
    print("THRESHOLD    | PRECISION  | RECALL     | TOTAL SIGNALS")
    print("--------------------------------------------------------")
    
    for t in [0.50, 0.52, 0.55, 0.58, 0.60, 0.62, 0.65, 0.68, 0.70]:
        y_pred_stat = (preds >= t).astype(int)
        total_signals = np.sum(y_pred_stat)
        
        if total_signals > 0:
            true_positives = np.sum((y_pred_stat == 1) & (y_test == 1))
            precision = true_positives / total_signals
            recall = true_positives / np.sum(y_test)
            print(f"{t*100:<12.1f}% | {precision:<10.2f} | {recall:<10.2f} | {total_signals:<13}")
    print("========================================================")
    
    # Save the updated model payload along with the new feature headers
    payload = {"model": model, "features": feature_cols}
    with open("meta_brain_lgb.pkl", "wb") as f:
        pickle.dump(payload, f)
    print("\n💾 Inter-Market Model Payload successfully saved -> meta_brain_lgb.pkl")

if __name__ == "__main__":
    main()