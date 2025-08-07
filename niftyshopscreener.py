symbols = [your nifty 50 symbols goes here]

for symbol in symbols:
    try:
        df = Instruments.get_historical_data(symbol, start_date, end_date)

        if df is None or df.empty or 'Close' not in df.columns:
            continue

        df = df.sort_index()
        df['20DMA'] = df['Close'].rolling(window=20).mean()

        latest_close = df['Close'].iloc[-1]
        latest_dma = df['20DMA'].iloc[-1]

        if pd.isna(latest_dma):
            continue

        deviation = ((latest_close - latest_dma) / latest_dma) * 100

        if latest_close < latest_dma:
            results.append((symbol, deviation))

        time.sleep(1)

    except Exception as e:
        logging.exception("Tools : NiftyShop - Error while fetching eligible stocks")
        print("Error while fetching eligible stocks")

top_5_symbols = [symbol for symbol, _ in sorted(results, key=lambda x: x[1])[:5]]
print(top_5_symbols)