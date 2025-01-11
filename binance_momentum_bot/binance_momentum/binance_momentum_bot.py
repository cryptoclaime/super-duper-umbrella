import time
from binance.client import Client
from binance.enums import SIDE_BUY, SIDE_SELL
import pandas as pd
from ta.momentum import RSIIndicator
import schedule
from dotenv import load_dotenv
import os

# Load environment variables
load_dotenv()

# Environment variables
API_KEY = os.getenv("BINANCE_API_KEY")
API_SECRET = os.getenv("BINANCE_API_SECRET")
LEVERAGE = int(os.getenv("LEVERAGE", 14))
INVESTMENT = float(os.getenv("INVESTMENT", 3))
PROFIT_TARGET = float(os.getenv("PROFIT_TARGET", 0.1))
MOMENTUM_THRESHOLD = float(os.getenv("MOMENTUM_THRESHOLD", 1.5))

# Initialize Binance Client
client = Client(API_KEY, API_SECRET)

print("Momentum Bot started with .env configuration")

# Parameters
CANDLE_INTERVAL_SHORT = Client.KLINE_INTERVAL_1MINUTE  # Short interval for momentum detection
CANDLE_INTERVAL_LONG = Client.KLINE_INTERVAL_15MINUTE  # Long interval for RSI

# Fetch all USDT-M futures trading pairs excluding BTC pairs
def get_all_futures_symbols():
    try:
        exchange_info = client.futures_exchange_info()
        symbols = [
            item['symbol'] for item in exchange_info['symbols'] 
            if 'USDT' in item['symbol'] and not item['symbol'].startswith("BTC")
        ]
        print(f"Filtered {len(symbols)} USDT-M futures symbols excluding BTC pairs")
        return symbols
    except Exception as e:
        print(f"Error fetching futures symbols: {e}")
        return []

# Fetch candlestick data
def get_candle_data(symbol, interval, limit=50):
    try:
        candles = client.futures_klines(symbol=symbol, interval=interval, limit=limit)
        df = pd.DataFrame(candles, columns=[
            "open_time", "open", "high", "low", "close", "volume", "close_time",
            "quote_asset_volume", "number_of_trades", "taker_buy_base_asset_volume",
            "taker_buy_quote_asset_volume", "ignore"
        ])
        df["close"] = pd.to_numeric(df["close"])
        return df
    except Exception as e:
        print(f"Error fetching data for {symbol}: {e}")
        return None

# Detect momentum
def detect_momentum(df):
    try:
        price_change = ((df["close"].iloc[-1] - df["close"].iloc[-2]) / df["close"].iloc[-2]) * 100
        if price_change > MOMENTUM_THRESHOLD:
            return "LONG"
        elif price_change < -MOMENTUM_THRESHOLD:
            return "SHORT"
        else:
            return "WAIT"
    except Exception as e:
        print(f"Error detecting momentum: {e}")
        return "WAIT"

# Analyze market using RSI
def analyze_rsi(df):
    try:
        rsi = RSIIndicator(df["close"], window=14).rsi()
        latest_rsi = rsi.iloc[-1]
        if latest_rsi < 30:
            return "LONG"
        elif latest_rsi > 70:
            return "SHORT"
        else:
            return "WAIT"
    except Exception as e:
        print(f"Error analyzing RSI: {e}")
        return "WAIT"

# Place order
def place_order(symbol, side, quantity):
    try:
        if side == "LONG":
            order = client.futures_create_order(
                symbol=symbol,
                side=SIDE_BUY,
                type="MARKET",
                quantity=quantity
            )
        elif side == "SHORT":
            order = client.futures_create_order(
                symbol=symbol,
                side=SIDE_SELL,
                type="MARKET",
                quantity=quantity
            )
        print(f"Order placed: {order}")
        return order
    except Exception as e:
        print(f"Error placing order: {e}")
        return None

# Monitor position and close at target profit
def monitor_position(symbol, entry_price, target_profit):
    try:
        while True:
            position = client.futures_position_information(symbol=symbol)
            for pos in position:
                if pos["symbol"] == symbol and float(pos["positionAmt"]) != 0:
                    current_price = float(client.futures_mark_price(symbol=symbol)["markPrice"])
                    pnl = (current_price - entry_price) * float(pos["positionAmt"])
                    if pnl >= target_profit:
                        side = SIDE_SELL if float(pos["positionAmt"]) > 0 else SIDE_BUY
                        client.futures_create_order(
                            symbol=symbol,
                            side=side,
                            type="MARKET",
                            quantity=abs(float(pos["positionAmt"]))
                        )
                        print(f"Position closed for {symbol} with profit: {pnl}")
                        return True
            time.sleep(5)
    except Exception as e:
        print(f"Error monitoring position: {e}")
        return False

# Main bot logic
def bot_logic():
    symbols = get_all_futures_symbols()
    for coin in symbols:
        print(f"Analyzing {coin}")
        # Fetch short interval data for momentum detection
        short_df = get_candle_data(coin, CANDLE_INTERVAL_SHORT)
        if short_df is not None:
            action_momentum = detect_momentum(short_df)
        
        # Fetch long interval data for RSI analysis
        long_df = get_candle_data(coin, CANDLE_INTERVAL_LONG)
        if long_df is not None:
            action_rsi = analyze_rsi(long_df)
        
        # Combine both signals
        if action_momentum != "WAIT" and action_momentum == action_rsi:
            action = action_momentum
            price = short_df["close"].iloc[-1]
            quantity = round(INVESTMENT / price, 4)
            print(f"Action for {coin}: {action}, Quantity: {quantity}")
            order = place_order(coin, action, quantity)
            if order:
                entry_price = float(order["fills"][0]["price"])
                monitor_position(coin, entry_price, PROFIT_TARGET)

# Schedule bot to run every 1 minute
schedule.every(1).minutes.do(bot_logic)

# Run the bot
if __name__ == "__main__":
    while True:
        schedule.run_pending()
        time.sleep(1)
