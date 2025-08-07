# ------------------------------------------------------------------------------------
#                          FabTrader Algorithmic Trading Platform
# ------------------------------------------------------------------------------------
# Copyright (c) 2022 FabTrader (Unit of Rough Sketch Company)
#
# LICENSE: PROPRIETARY SOFTWARE
# - This software is the exclusive property of FabTrader.
# - Unauthorized copying, modification, distribution, or use is strictly prohibited.
# - Written permission from the author is required for any use beyond personal,
#   non-commercial purposes.
#
# CONTACT:
# - Website: https://fabtrader.in
# - Email: hello@fabtrader.in
#
# Usage: Internal use only. Not for commercial redistribution.
# Permissions and licensing inquiries should be directed to the contact email.

"""
    Strategy Name : Aditi (Nifty Shop)
    Description : Stocks that have fallen farthest below 20DMA is bought (as set by daily buy count limit)
                  Stocks (average buy price) that reached Target% is sold (as set by daily sell count limit)
                  Averaging : If all eligible stocks for the day are part of holding, then average (down)
                  the stock (part of our holding) that has fallen the most below 5%
    Indicators : 20 DMA
    Entry : Lowest from 20DMA across 50 Stocks
    Exit :  minimum 5% return (Stock with highest return above 5% is sold)
    Stop Loss : None
    Universe : NIFTY 50
    Timing : Positional (3:20 pm every day)
    Timeframe : Daily
"""
    
        # Initialize all the strategy properties
        self.name = 'Aditi'
        self.enabled = self.is_enabled()
        self.product_type = ProductType.CNC
        self.start_timestamp = Utils.get_time_of_day(15, 25, 0)
        self.stop_timestamp = Utils.get_time_of_day(15, 29, 0)  
        self.universe = 'nifty50'
        self.blacklist_stocks = []
        self.symbols = []
        # Strategy specific variables
        self.scan_complete = False
        self.investment_first_buy = 15_000
        self.investment_averaging = 7_500
        self.target_pct = 5.0       # Target percentage
        self.averaging_pct = -5.0  # % a stock should fall (minimum) to be eligible for averaging
        self.max_buys_per_day = 1  # How many stock(s) to buy in a day
        self.max_sells_per_day = 1 # How many stock(s) to sell in a day
        self.max_averaging_per_stock = 3  # A stock will only be averaged down max this many times


    def execute_strategy(self):

        # Execute sell leg to close Stock that has hit the target returns
        self.initiate_sell()
        time.sleep(30)

        # Get list of top 5 eligible Stocks
        stock_list = self.get_eligible_stocks_for_today()

        if not stock_list:
            logging.info("%s: No Eligible Stocks for buying today", self.get_name())
            return

        logging.info('%s: Eligible Stocks for today', self.get_name())
        logging.info(str(stock_list)[1:-1])
        self.initiate_buy(stock_list)

    def get_eligible_stocks_for_today(self):

        # Get the list of stocks (Nifty 50)
        self.get_universe_instruments()

        # Function: Calculates price fall% from 20DMA and select top 5 Stocks from that list
        if len(self.symbols) == 0:
            logging.exception("%s: Error while fetching stock list from Nifty universe. Skipping strategy",
                              self.get_name())
            return

        results, end_date = [], date.today()
        start_date = end_date - timedelta(days=50)  # To ensure we have at least 20 days of data

        for symbol in self.symbols:
            try:
                df = SymbolManager.get_historical_data(symbol, start_date, end_date)

                if df is None or df.empty or 'Close' not in df.columns:
                    continue

                df = df.sort_index()  # Fix - Sometimes data provided is not properly index on date
                df['20DMA'] = df['Close'].rolling(window=20).mean()

                latest_close = df['Close'].iloc[-1]
                latest_dma = df['20DMA'].iloc[-1]

                if pd.isna(latest_dma):
                    continue

                deviation = ((latest_close - latest_dma) / latest_dma) * 100

                if latest_close < latest_dma:
                    results.append((symbol, deviation))

            except Exception as e:
                logging.exception("%s: Error while fetching eligible stocks", self.get_name())

        # Extract just the top 5 symbols that are the farthest below 20DMA
        top_5_symbols = [symbol for symbol, _ in sorted(results, key=lambda x: x[1])[:5]]
        return top_5_symbols

    def initiate_buy(self, stock_list):

        new_stocks_bought = 0

        for stock in stock_list:

            # Check if the stock is already held. If so skip.
            already_held = any(
                t.tradingSymbol == stock
                for t in TradeManager.trades
                if t.strategy == self.name and t.tradeState == 'active'
            )

            # If not already part of holding, buy stock
            if not already_held and new_stocks_bought < self.max_buys_per_day:
                logging.info("%s: Initiating Buy for stock: %s", self.get_name(), stock)
                self.place_new_trade(stock)
                new_stocks_bought += 1

        # If there has been any buy, then return
        if new_stocks_bought > 0:
            return

        logging.info("%s: No new Stocks - All Stocks screened are already part of holding."
             " Checking existing holdings for averaging..",self.get_name())

        # Averaging logic ------------------------------------------------
        # If all the 5 eligible Stocks are already part of our holding, then check all stocks in holding and
        # find ones have fallen further below -5%. Choose the one that has fallen the most and buy it for averaging

        # Consolidate all trades for strategy in a list
        rows = [
            {
                'Symbol': t.tradingSymbol,
                'LastBuyPrice': t.entry,
                'Date': t.createTimestamp
            }
            for t in TradeManager.trades
            if (t.strategy == self.name
                and t.tradeState == 'active'
                and t.targetOrder is None
                and t.entryOrder.orderStatus == OrderStatus.COMPLETE
                and t.entryOrder.filledQty > 0)
        ]

        df = pd.DataFrame(rows)
        if df.empty:
            logging.info("%s: No Stocks in holding have fallen below threshold. "
                         "No buy trades for today", self.get_name())
            return

        # Keep only the latest purchase per symbol
        df = df.loc[df.groupby('Symbol')['Date'].idxmax()]

        # Compute % change vs CMP
        df['Close'] = df['Symbol'].apply(self.get_cmp)
        df['ChangePct'] = ((df['Close'] - df['LastBuyPrice']) /
                           df['LastBuyPrice'] * 100).round(2)

        df = df[df['ChangePct'] <= self.averaging_pct].sort_values('ChangePct')

        # Enforce max-averaging limit
        df['AvgCount'] = df['Symbol'].apply(self._current_averaging_count)
        df = df[df['AvgCount'] < self.max_averaging_per_stock]

        if not df.empty:
            averaging_symbol = df.iloc[0]['Symbol']
            logging.info("%s: Averaging candidate: %s (%.2f%%) – already averaged %d time(s)",
                         self.get_name(), averaging_symbol, df.iloc[0]['ChangePct'],
                         df.iloc[0]['AvgCount'])
            self.place_new_trade(averaging_symbol)
        else:
            logging.info("%s: No stock eligible for averaging (limit reached or none < -5%%)",
                         self.get_name())

    def initiate_sell(self):
        """
        Square-off up to `max_sells_per_day` *symbols* whose *aggregate* unrealised
        P&L (based on weighted-average entry price) is ≥ target_pct.
        If more than max_sells_per_day qualify, the top N by highest P&L % are chosen.
        """

        # Build {symbol: [list of active trades]}
        symbol_trades = {}
        for trade in TradeManager.trades:
            if (trade.strategy == self.name
                    and trade.tradeState == 'active'
                    and trade.targetOrder is None
                    and trade.entryOrder.orderStatus == OrderStatus.COMPLETE
                    and trade.entryOrder.filledQty > 0):
                symbol_trades.setdefault(trade.tradingSymbol, []).append(trade)

        candidates = []
        for symbol, trades in symbol_trades.items():
            total_qty = sum(t.filledQty for t in trades)
            if total_qty == 0:
                continue

            weighted_entry = sum(t.entry * t.filledQty for t in trades) / total_qty
            cmp = self.get_cmp(symbol)
            if cmp is None:
                continue

            unrealised_pnl = total_qty * (cmp - weighted_entry)
            pnl_pct = Utils.round_off_price(unrealised_pnl * 100 / (total_qty * weighted_entry))

            if pnl_pct >= self.target_pct:
                candidates.append((symbol, pnl_pct, trades))

        if not candidates:
            logging.info("%s: No symbol meets the aggregate target %.1f%%", self.get_name(), self.target_pct)
            return

        # Sort by highest aggregate P&L %
        candidates.sort(key=lambda x: x[1], reverse=True)
        to_sell = candidates[:self.max_sells_per_day]

        for symbol, pnl_pct, trades in to_sell:
            logging.info("%s: Selling %s (aggregate P&L %.2f%%)", self.get_name(), symbol, pnl_pct)
            for trade in trades:
                TradeManager.square_off_trade(trade)

        logging.info("%s: Total symbols sold today: %d", self.get_name(), len(to_sell))

    def _current_averaging_count(self, symbol: str) -> int:
        """Return how many times this symbol has already been averaged (bought)."""
        return sum(
            1
            for t in TradeManager.trades
            if (t.strategy == self.name
                and t.tradingSymbol == symbol
                and t.direction == Direction.LONG
                and t.entryOrder is not None
                and t.entryOrder.orderStatus == OrderStatus.COMPLETE
                and t.entryOrder.filledQty > 0)
        )

 