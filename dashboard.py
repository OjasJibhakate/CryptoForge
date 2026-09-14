# ===========================================================================
# CRYPTOFORGE MATRIX TERMINAL :: ISOLATED RADIO-SWITCH ARCHITECTURE
# ===========================================================================
import streamlit as st
import pandas as pd
import numpy as np
import os
import plotly.graph_objects as go

st.set_page_config(page_title="CryptoForge Matrix Terminal", layout="wide", initial_sidebar_state="expanded")

# Custom CSS for Institutional Dark Theme
st.markdown("""
    <style>
    .reportview-container { background: #0e1117; }
    h1, h2, h3 { color: #ffffff; }
    </style>
""", unsafe_allow_html=True)

# =====================================================================
# ⚙️ SIDEBAR DYNAMIC SWITCHBOARD (DOT-CLICK METHOD)
# =====================================================================
st.sidebar.title("⚡ CryptoForge Matrix")
st.sidebar.markdown("---")

# 🔘 THE DOT-CLICK TOGGLE (Radio Buttons)
active_strategy = st.sidebar.radio(
    "Active Strategy Architecture",
    ["Strategy 1: Micro Scalper (0.5%)", "Strategy 2: Macro Breakout (2.0%)"]
)

st.sidebar.markdown("---")
st.sidebar.subheader("Global Capital Allocation")
starting_capital = st.sidebar.number_input("Starting Capital ($)", value=1000.00, step=100.00)
leverage = st.sidebar.slider("Account Leverage", min_value=1, max_value=20, value=5)

# =====================================================================
# 🧠 DYNAMIC ROUTING LOGIC
# =====================================================================
if active_strategy == "Strategy 1: Micro Scalper (0.5%)":
    file_path = "crypto_live_trades.csv"
    target_pct = 0.0050  # 🛠️ Math officially corrected to 0.50%
    stop_pct = 0.0050    
    theme_color = "#ff4b4b" # Red Matrix
    strat_title = "STRATEGY 1 :: HIGH-FREQUENCY MICRO SCALPER"
    strat_desc = "Hunting fast 1-minute velocity spikes with tight 0.50% profit buffers."
else:
    file_path = "crypto_live_trades_2.csv"
    target_pct = 0.0200  # 2.0%
    stop_pct = 0.0100    # 1.0%
    theme_color = "#00f2fe" # Neon Blue Matrix
    strat_title = "STRATEGY 2 :: INSTITUTIONAL MACRO BREAKOUT"
    strat_desc = "Hunting structural 2.0% multi-candle trends with extended wick armor."

# =====================================================================
# 🧮 MATH QUANT ENGINE (WITH SCENARIO CURVES)
# =====================================================================
def get_isolated_metrics():
    if not os.path.exists(file_path):
        return None
    try:
        df = pd.read_csv(file_path)
        if df.empty:
            return None
            
        closed = df[df['status'].isin(['WIN', 'LOSS'])].copy().reset_index(drop=True)
        
        equity_curve = [0.0]
        base_curve = [0.0]
        upper_band = [0.0]
        lower_band = [0.0]
        cumulative = 0.0
        wins = 0
        
        for idx, row in closed.iterrows():
            if row['status'] == 'WIN':
                trade_pnl = starting_capital * target_pct * leverage
                wins += 1
            else:
                trade_pnl = -(starting_capital * stop_pct * leverage)
                
            cumulative += trade_pnl
            equity_curve.append(cumulative)
            
            # Reconstruct the 4-line mathematical boundaries for clean visual tracking
            base_curve.append(cumulative * 0.70)
            upper_band.append(cumulative + (starting_capital * 0.05))
            lower_band.append(cumulative - (starting_capital * 0.05))
            
        total = len(closed)
        win_rate = (wins / total * 100) if total > 0 else 0.0
        expectancy = (cumulative / total) if total > 0 else 0.0
        pending = len(df[df['status'] == 'OPEN'])
        
        return {
            "total": total, "win_rate": win_rate, "pnl": cumulative,
            "expectancy": expectancy, "pending": pending, "raw": df,
            "curve": equity_curve, "base": base_curve, "upper": upper_band, "lower": lower_band
        }
    except:
        return None

strat_data = get_isolated_metrics()

# =====================================================================
# 🖥️ DYNAMIC MAIN PAGE VIEW
# =====================================================================
st.title(f"Stream: CRYPTO UNIVERSE | {strat_title}")
st.markdown(f"*{strat_desc}*")
st.markdown("---")

if strat_data:
    # --- FULL WIDTH CORE METRICS ---
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Unfiltered Trades", strat_data["total"])
    m2.metric("Filtered Win Rate", f"{strat_data['win_rate']:.1f}%")
    m3.metric("Filtered Net PnL", f"${strat_data['pnl']:.2f}")
    m4.metric("AI Expectancy (Per Trade)", f"${strat_data['expectancy']:.2f}")
    
    st.info(f"⚡ {strat_data['pending']} trades currently pending live in active market runtime.")
    st.markdown("---")
    
    # --- OMNI-MATRIX SCENARIO CURVES ---
    st.subheader("📊 Omni-Matrix Scenario Curves")
    fig = go.Figure()
    
    # Line 1: Actual Target Performance Curve
    fig.add_trace(go.Scatter(y=strat_data["curve"], mode='lines+markers', name='Actual Performance Curve', line=dict(color=theme_color, width=3), marker=dict(size=6)))
    # Line 2: Signal Core Baseline
    fig.add_trace(go.Scatter(y=strat_data["base"], mode='lines', name='Signal Core Baseline', line=dict(color='#a61b1b', width=2, dash='dash')))
    # Line 3: Alpha Variance Channel (Upper)
    fig.add_trace(go.Scatter(y=strat_data["upper"], mode='lines', name='Alpha Upper Limit', line=dict(color='#ffb703', width=1.5)))
    # Line 4: Alpha Variance Channel (Lower)
    fig.add_trace(go.Scatter(y=strat_data["lower"], mode='lines', name='Alpha Lower Floor', line=dict(color='#0072ff', width=1.5)))
    
    fig.update_layout(
        template="plotly_dark",
        paper_bgcolor='rgba(0,0,0,0)',
        plot_bgcolor='rgba(0,0,0,0)',
        xaxis_title="Number of Executed Trades",
        yaxis_title="Net Profit / Loss ($)",
        margin=dict(l=20, r=20, t=20, b=20),
        hovermode="x unified"
    )
    st.plotly_chart(fig, use_container_width=True)
    
    # --- EXCLUSIVE LOG AUDIT TRAIL ---
    st.markdown("---")
    st.subheader("📋 Strategy Audit Trail Ledger")
    st.dataframe(strat_data["raw"].tail(50), use_container_width=True)

else:
    # Beautiful empty state if file doesn't exist yet
    st.warning(f"⚠️ Pipeline Empty: The ledger file `{file_path}` was not found or has no recorded closed trades.")
    st.markdown(f"Execute the Python engine for **{active_strategy}** and wait for the first execution to close to build the data matrix.")