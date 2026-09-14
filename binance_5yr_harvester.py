# ===========================================================================
# CRYPTOFORGE :: MULTI-ASSET 5-YEAR HARVESTER (V2.1 - PATCHED)
# ===========================================================================
import os
import urllib.request
import zipfile
import pandas as pd

# 🎯 The Verified Quantitative Tier-List (June 2026)
# 🎯 The Verified Quantitative Tier-List for the Historical Training Vault
TARGET_SYMBOLS = ['BTCUSDT', 'ETHUSDT', 'SPCXUSDT', 'SOLUSDT', 'HYPEUSDT', '1000PEPEUSDT']

BASE_URL = "https://data.binance.vision/data/futures/um/monthly/klines/{symbol}/1m/{symbol}-1m-{year}-{month}.zip"
DOWNLOAD_DIR = "binance_raw_zips"
DATA_VAULT = "Crypto_Historical_Vault"

# Create secure directories if they don't exist
if not os.path.exists(DOWNLOAD_DIR): 
    os.makedirs(DOWNLOAD_DIR)
if not os.path.exists(DATA_VAULT): 
    os.makedirs(DATA_VAULT)

def harvest_data(start_year=2021, end_year=2026):
    for symbol in TARGET_SYMBOLS:
        print(f"\n========================================================")
        print(f"🚀 INITIATING HARVEST FOR: {symbol}")
        print(f"========================================================")
        
        all_csv_files = []
        
        # Systematically knock on the Binance AWS Buckets
        for year in range(start_year, end_year + 1):
            for month in range(1, 13):
                month_str = f"{month:02d}"
                file_name = f"{symbol}-1m-{year}-{month_str}.zip"
                url = BASE_URL.format(symbol=symbol, year=year, month=month_str)
                save_path = os.path.join(DOWNLOAD_DIR, file_name)
                
                try:
                    urllib.request.urlretrieve(url, save_path)
                    
                    # Extract the CSV from the ZIP
                    with zipfile.ZipFile(save_path, 'r') as zip_ref:
                        zip_ref.extractall(DOWNLOAD_DIR)
                        extracted_csv = os.path.join(DOWNLOAD_DIR, file_name.replace('.zip', '.csv'))
                        all_csv_files.append(extracted_csv)
                        
                    # Burn the zip immediately to save hard drive space
                    os.remove(save_path) 
                    
                except urllib.error.HTTPError:
                    # 🛡️ THE TIME-TRAVEL SHIELD: 
                    # Silently skips months/years before the coin was officially launched
                    pass 
                except Exception as e:
                    print(f"🚨 Network Error on {year}-{month_str}: {e}")
                
        # ⚙️ Merge the specific coin's data
        if all_csv_files:
            print(f"⚙️ Merging {len(all_csv_files)} months of {symbol} data...")
            
            # Binance kline standard columns
            cols = ['timestamp', 'Open', 'High', 'Low', 'Close', 'Volume', 
                    'close_time', 'qav', 'num_trades', 'tbbav', 'tbqav', 'ignore']
            
            df_list = [pd.read_csv(f, names=cols, header=None) for f in all_csv_files]
            
            master_df = pd.concat(df_list, ignore_index=True)
            
            # 🛡️ THE HEADER CRUSHER: 
            # Force timestamps to numeric; any text headers ("open_time") become NaN and get dropped
            master_df = master_df[pd.to_numeric(master_df['timestamp'], errors='coerce').notna()]
            master_df['timestamp'] = pd.to_numeric(master_df['timestamp']).astype(int)
            
            # Clean timestamps for the AI model
            master_df['timestamp'] = pd.to_datetime(master_df['timestamp'], unit='ms')
            master_df.sort_values('timestamp', inplace=True)
            
            # Save to the isolated quantitative vault
            final_csv_path = os.path.join(DATA_VAULT, f"{symbol}_MASTER_1M.csv")
            master_df.to_csv(final_csv_path, index=False)
            
            # Clean up individual unzipped monthly CSVs to keep the workspace spotless
            for f in all_csv_files:
                if os.path.exists(f):
                    os.remove(f)
            
            print(f"✅ {symbol} SECURED: {len(master_df):,} rows -> {final_csv_path}")
        else:
            print(f"⚠️ No data found for {symbol} in the requested timeframe.")

if __name__ == "__main__":
    # Pulling data from 2021 through current year 2026
    harvest_data(2021, 2026)