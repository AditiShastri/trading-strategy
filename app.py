import streamlit as st
import pandas as pd
import yfinance as yf
from datetime import date, timedelta
import time
import requests

# --- Core Strategy Logic (adapted from your scripts) ---
"""
Fetches Nifty 50 symbols dynamically from NSE India. Falls back to static list if request fails.
"""   
def get_nifty50_symbols():
    url = "https://www.nseindia.com/api/equity-stockIndices?index=NIFTY%2050"
    headers = {
        "User-Agent": "Mozilla/5.0",
        "Accept-Language": "en-US,en;q=0.9",
        "Accept-Encoding": "gzip, deflate, br",
        "Accept": "application/json"
    }
    try:
        with requests.Session() as s:
            # Visit homepage to get cookies
            s.get("https://www.nseindia.com", headers=headers, timeout=10)
            response = s.get(url, headers=headers, timeout=10)
            if response.status_code != 200 or not response.text.strip():
                print(f"Request failed: {response.status_code}")
                print(f"Content: {response.text[:500]}")
                raise Exception("Empty or invalid response from NSE API")
            try:
                data = response.json()
            except Exception:
                print(f"Non-JSON content: {response.text[:500]}")
                raise Exception("Response was not JSON, likely blocked or redirected")
            symbols = [item['symbol'] + ".NS" for item in data.get('data', [])]
            if symbols:
                return symbols
    except Exception as e:
        print(f"Error: {e}")
        # Return fallback static list here if desired
        return [
            'RELIANCE.NS', 'TCS.NS', 'HDFCBANK.NS', 'ICICIBANK.NS', 'INFY.NS',
            'HINDUNILVR.NS', 'BHARTIARTL.NS', 'ITC.NS', 'SBIN.NS', 'LICI.NS',
            'BAJFINANCE.NS', 'HCLTECH.NS', 'KOTAKBANK.NS', 'MARUTI.NS', 'LT.NS',
            'ASIANPAINT.NS', 'AXISBANK.NS', 'SUNPHARMA.NS', 'WIPRO.NS', 'ULTRACEMCO.NS',
            'NESTLEIND.NS', 'BAJAJFINSV.NS', 'ADANIENT.NS', 'NTPC.NS', 'M&M.NS',
            'JSWSTEEL.NS', 'TATAMOTORS.NS', 'POWERGRID.NS', 'TITAN.NS', 'TATASTEEL.NS',
            'ADANIPORTS.NS', 'COALINDIA.NS', 'ONGC.NS', 'INDUSINDBK.NS', 'HINDALCO.NS',
            'BRITANNIA.NS', 'CIPLA.NS', 'DRREDDY.NS', 'EICHERMOT.NS', 'GRASIM.NS',
            'HEROMOTOCO.NS', 'BPCL.NS', 'DIVISLAB.NS', 'BAJAJ-AUTO.NS', 'APOLLOHOSP.NS',
            'TECHM.NS', 'UPL.NS', 'SHREECEM.NS', 'HDFCLIFE.NS', 'TATACONSUM.NS'
        ]
        

@st.cache_data(ttl=3600) # Cache data for 1 hour
def get_historical_data(symbol, start_date, end_date):
    """
    Fetches historical stock data using yfinance and handles potential
    duplicate index entries.
    """
    try:
        df = yf.download(symbol, start=start_date, end=end_date, progress=False, auto_adjust=True)
        if df.empty:
            return None
        # FIX: Ensure the index is unique by removing duplicate dates, keeping the last entry.
        df = df.loc[~df.index.duplicated(keep='last')]
        return df
    except Exception as e:
        # This error will now be more informative if it still occurs.
        st.error(f"Could not fetch or process data for {symbol}: {e}")
        return None

def get_eligible_stocks_for_today(symbols, progress_bar):
    """
    Calculates price fall % from 20DMA and selects the top 5 stocks.
    """
    results = []
    end_date = date.today()
    start_date = end_date - timedelta(days=50)

    total_symbols = len(symbols)
    for i, symbol in enumerate(symbols):
        try:
            df = get_historical_data(symbol, start_date, end_date)

            if df is None or df.empty or 'Close' not in df.columns or len(df) < 20:
                continue

            df = df.sort_index()
            df['20DMA'] = df['Close'].rolling(window=20).mean()

            # Robust extraction for latest_close and latest_dma
            latest_close = df['Close'].iloc[-1]
            if isinstance(latest_close, pd.Series):
                latest_close = latest_close.item()
            latest_dma = df['20DMA'].iloc[-1]
            if isinstance(latest_dma, pd.Series):
                latest_dma = latest_dma.item()

            if pd.isna(latest_dma) or pd.isna(latest_close):
                continue

            if latest_close < latest_dma:
                deviation = ((latest_close - latest_dma) / latest_dma) * 100
                results.append({'Symbol': symbol, 'Deviation (%)': deviation, 'CMP': latest_close, '20 DMA': latest_dma})

        except Exception as e:
            # Catching potential errors during the processing of each symbol
            st.warning(f"Skipping {symbol} due to an error: {e}")
            continue

        # Update progress bar
        progress_bar.progress((i + 1) / total_symbols, text=f"Scanning: {symbol}")
        time.sleep(0.05) # Small delay to make the progress bar visible

    # Sort by the most deviation (most negative) and return as a DataFrame
    if not results:
        return pd.DataFrame()

    results_df = pd.DataFrame(results)
    top_5_df = results_df.sort_values(by='Deviation (%)').head(5)
    return top_5_df

def get_current_holdings(uploaded_file):
    """Parses the uploaded trade export to find active holdings."""
    if uploaded_file is None:
        return pd.DataFrame()
    try:
        # Reset file pointer to allow re-reading if necessary
        uploaded_file.seek(0)
        df = pd.read_csv(uploaded_file)
        # Filter for active trades for the 'Aditi' strategy
        # Ensure column names match your CSV file exactly.
        active_trades = df[(df['Strategy'] == 'Aditi') & (df['Status'] == 'active')]
        return active_trades
    except Exception as e:
        st.error(f"Error reading or processing the uploaded file: {e}")
        return pd.DataFrame()


# --- Streamlit UI ---

st.set_page_config(page_title="Nifty Shop Screener", layout="wide")

st.title("📈 Nifty Shop Strategy Screener")
st.markdown("An interactive tool to screen stocks based on the 'Aditi' (Nifty Shop) strategy.")

# --- Sidebar for Parameters and Controls ---
with st.sidebar:
    st.header("⚙️ Strategy Parameters")

    investment_first_buy = st.number_input("Investment for First Buy (₹)", value=15000, step=1000)
    investment_averaging = st.number_input("Investment for Averaging (₹)", value=7500, step=500)
    target_pct = st.number_input("Target Profit (%)", value=5.0, step=0.5, format="%.2f")
    averaging_pct = st.number_input("Averaging Trigger Fall (%)", value=-5.0, step=-0.5, format="%.2f", help="A stock must fall by this percentage from its last buy price to be considered for averaging.")
    max_buys_per_day = st.slider("Max Buys per Day", 1, 5, 1)
    max_sells_per_day = st.slider("Max Sells per Day", 1, 5, 1)
    max_averaging_per_stock = st.slider("Max Averaging per Stock", 1, 10, 3)

    st.header("📄 Trade Data")
    uploaded_file = st.file_uploader("Upload your trade history CSV", type=['csv'])

    run_button = st.button("🚀 Run Strategy", type="primary", use_container_width=True)


# --- Main Content Area ---
if run_button:
    st.header("📊 Strategy Results")
    nifty50_symbols = get_nifty50_symbols()

    # --- 1. Stock Screening ---
    with st.spinner("Scanning Nifty 50 stocks... This may take a moment."):
        progress_bar = st.progress(0, text="Starting scan...")
        eligible_stocks_df = get_eligible_stocks_for_today(nifty50_symbols, progress_bar)
        progress_bar.empty() # Clear the progress bar after completion

    st.subheader("🎯 Top 5 Eligible Stocks for Buying")
    if not eligible_stocks_df.empty:
        st.dataframe(eligible_stocks_df.style.format({
            'Deviation (%)': '{:.2f}%',
            'CMP': '₹{:.2f}',
            '20 DMA': '₹{:.2f}'
        }), use_container_width=True)
    else:
        st.info("No stocks are currently trading below their 20-Day Moving Average.")


    # --- 2. Holdings and Decisions ---
    st.subheader("💼 Current Holdings & Decisions")
    holdings_df = get_current_holdings(uploaded_file)

    if uploaded_file is None:
        st.warning("Please upload your trade history CSV to see Buy/Sell/Average decisions.")
    else:
        col1, col2 = st.columns(2)

        with col1:
            st.write("**Current Active Holdings (Aditi Strategy)**")
            if not holdings_df.empty:
                # Ensure the required columns exist before trying to display them
                display_cols = [col for col in ['Symbol', 'Filled Qty', 'Entry', 'Pnl%'] if col in holdings_df.columns]
                st.dataframe(holdings_df[display_cols], use_container_width=True)
            else:
                st.info("No active holdings found in the uploaded file for the 'Aditi' strategy.")

        with col2:
            st.write("**Today's Recommended Actions**")
            # --- Buy/Average Logic ---
            buy_decisions = []
            held_symbols = holdings_df['Symbol'].tolist() if not holdings_df.empty else []
            new_stocks_bought = 0

            if not eligible_stocks_df.empty:
                for index, row in eligible_stocks_df.iterrows():
                    stock = row['Symbol']
                    if stock not in held_symbols and new_stocks_bought < max_buys_per_day:
                        buy_decisions.append(f"🟢 **BUY**: {stock} (New position)")
                        new_stocks_bought += 1

            # Averaging Logic
            if new_stocks_bought == 0 and not eligible_stocks_df.empty and not holdings_df.empty:
                st.info("All eligible stocks are already held. Checking for averaging opportunities.")
                potential_avg = []
                for index, row in holdings_df.iterrows():
                    symbol = row['Symbol']
                    # Use the already fetched CMP from screening if available
                    cmp_row = eligible_stocks_df[eligible_stocks_df['Symbol'] == symbol]
                    if not cmp_row.empty:
                        cmp = cmp_row['CMP'].iloc[0]
                        change_pct = ((cmp - row['Entry']) / row['Entry']) * 100
                        if change_pct <= averaging_pct:
                             potential_avg.append({'Symbol': symbol, 'ChangePct': change_pct})

                if potential_avg:
                    avg_df = pd.DataFrame(potential_avg).sort_values('ChangePct').iloc[0]
                    buy_decisions.append(f"🔵 **AVERAGE**: {avg_df['Symbol']} (Down {abs(avg_df['ChangePct']):.2f}%)")
                else:
                    buy_decisions.append("⚪️ **HOLD**: No new buys or averaging candidates found.")

            if not buy_decisions:
                 buy_decisions.append("⚪️ **HOLD**: No new buy recommendations.")

            for decision in buy_decisions:
                st.markdown(decision)

            # --- Sell Logic ---
            sell_decisions = []
            if not holdings_df.empty and 'Pnl%' in holdings_df.columns:
                sell_candidates = holdings_df[holdings_df['Pnl%'] >= target_pct]
                if not sell_candidates.empty:
                    # Sort by highest P&L to sell the best performers first
                    to_sell = sell_candidates.sort_values('Pnl%', ascending=False).head(max_sells_per_day)
                    for index, row in to_sell.iterrows():
                        sell_decisions.append(f"🔴 **SELL**: {row['Symbol']} (Profit: {row['Pnl%']:.2f}%)")
                else:
                     sell_decisions.append("⚪️ **HOLD**: No holdings have reached the target profit.")

            for decision in sell_decisions:
                st.markdown(decision)

else:
    st.info("Adjust the parameters in the sidebar and click 'Run Strategy' to see the analysis.")
    st.markdown("""
    ### How to Use:
    1.  **Adjust Parameters**: Set your desired investment amounts, profit targets, and limits in the sidebar on the left.
    2.  **Upload Data**: Provide your trade history file. The app will use this to identify your current holdings and make sell/averaging decisions.
    3.  **Run Strategy**: Click the 'Run Strategy' button.
    4.  **Review Results**:
        * The app will scan Nifty 50 stocks and show you the top 5 that have fallen the most below their 20-Day Moving Average.
        * Based on your current holdings, it will recommend whether to **BUY** a new stock, **SELL** a profitable one, or **AVERAGE** down on an existing position.
    """)
