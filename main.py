import os
import threading
import requests
import pandas as pd
import numpy as np
from flask import Flask
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton

TOKEN = os.environ.get("BOT_TOKEN")
bot = telebot.TeleBot(TOKEN)

app = Flask(__name__)
@app.route('/')
def home():
    return "Forex Bot is LIVE!"

PAIRS = {
    "EUR/USD": "EURUSD=X",
    "GBP/USD": "GBPUSD=X",
    "USD/JPY": "USDJPY=X",
    "GOLD": "GC=F",
}

HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}

def get_close(symbol):
    # Direct Yahoo Chart API - works on Render, yfinance doesn't
    for host in ["query1.finance.yahoo.com", "query2.finance.yahoo.com"]:
        try:
            url = f"https://{host}/v8/finance/chart/{symbol}?range=5d&interval=15m"
            r = requests.get(url, headers=HEADERS, timeout=15)
            data = r.json()
            result = data['chart']['result'][0]
            closes = result['indicators']['quote'][0]['close']
            closes = [c for c in closes if c is not None]
            if len(closes) > 30:
                print(f"OK {symbol} got {len(closes)} candles from {host}")
                return pd.Series(closes)
        except Exception as e:
            print(f"Fail {host} {symbol}: {e}")
            continue
    # Fallback: Stooq daily
    try:
        stooq_map = {"EURUSD=X": "eurusd", "GBPUSD=X": "gbpusd", "USDJPY=X": "usdjpy", "GC=F": "xauusd"}
        s = stooq_map.get(symbol, "eurusd")
        url = f"https://stooq.com/q/d/l/?s={s}&i=d"
        df = pd.read_csv(url)
        if len(df) > 30:
            return pd.Series(df['Close'].values.astype(float))
    except Exception as e:
        print(f"Stooq fail {symbol}: {e}")
    return None

def analyze(symbol):
    try:
        close = get_close(symbol)
        if close is None:
            return None
        delta = close.diff()
        gain = delta.where(delta > 0, 0).rolling(14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
        rsi = 100 - (100 / (1 + (gain/loss)))
        ema20 = close.ewm(span=20).mean()
        ema50 = close.ewm(span=50).mean()
        ema12 = close.ewm(span=12).mean()
        ema26 = close.ewm(span=26).mean()
        macd = ema12 - ema26
        signal_line = macd.ewm(span=9).mean()
        sma20 = close.rolling(20).mean()
        std20 = close.rolling(20).std()
        upper = sma20 + (std20 * 2)
        lower = sma20 - (std20 * 2)
        low14 = close.rolling(14).min()
        high14 = close.rolling(14).max()
        stoch = 100 * (close - low14) / (high14 - low14)
        price = float(close.iloc[-1])
        r = float(rsi.iloc[-1]); e20 = float(ema20.iloc[-1]); e50 = float(ema50.iloc[-1])
        m = float(macd.iloc[-1]); s = float(signal_line.iloc[-1])
        up = float(upper.iloc[-1]); lo = float(lower.iloc[-1]); st = float(stoch.iloc[-1])
        votes = 0; details = []
        if r < 30: votes += 1; details.append("RSI: Oversold -> BUY")
        elif r > 70: votes -= 1; details.append("RSI: Overbought -> SELL")
        elif r < 50: votes += 0.5; details.append("RSI: Bullish")
        else: votes -= 0.5; details.append("RSI: Bearish")
        if price > e20 > e50: votes += 1; details.append("EMA: Uptrend -> BUY")
        elif price < e20 < e50: votes -= 1; details.append("EMA: Downtrend -> SELL")
        else: details.append("EMA: Sideways")
        if m > s: votes += 1; details.append("MACD: Bullish -> BUY")
        else: votes -= 1; details.append("MACD: Bearish -> SELL")
        if price <= lo: votes += 1; details.append("Bollinger: At Lower Band -> BUY")
        elif price >= up: votes -= 1; details.append("Bollinger: At Upper Band -> SELL")
        else: details.append("Bollinger: Middle")
        if st < 20: votes += 1; details.append("Stoch: Oversold -> BUY")
        elif st > 80: votes -= 1; details.append("Stoch: Overbought -> SELL")
        else: details.append("Stoch: Neutral")
        return price, r, e20, e50, m, s, up, lo, st, votes, details
    except Exception as e:
        print(f"Error {symbol}: {e}")
        return None

def make_signal(pair_name, symbol):
    res = analyze(symbol)
    if res is None:
        return f"❌ {pair_name}: Data not available, try again in 1 min."
    price, r, e20, e50, m, s, up, lo, st, votes, details = res
    if votes >= 3: sig, emoji = "STRONG BUY 🟢🟢 CALL ⬆️⬆️", "🟢"
    elif votes >= 1: sig, emoji = "BUY 🟢 CALL ⬆️", "🟢"
    elif votes <= -3: sig, emoji = "STRONG SELL 🔴🔴 PUT ⬇️⬇️", "🔴"
    elif votes <= -1: sig, emoji = "SELL 🔴 PUT ⬇️", "🔴"
    else: sig, emoji = "WAIT ⚪ NEUTRAL - NO TRADE", "⚪"
    detail_text = "\n".join([f"• {d}" for d in details])
    return (f"{emoji} **{pair_name}**\n💰 Price: `{price:.5f}`\n🎯 Signal: **{sig}**\n⭐ Score: `{votes}/5`\n\n📊 **Indicators:**\nRSI (14): `{r:.1f}`\nEMA 20: `{e20:.5f}` | EMA 50: `{e50:.5f}`\nMACD: `{m:.5f}` | Signal: `{s:.5f}`\nBollinger: `{lo:.5f} - {up:.5f}`\nStochastic: `{st:.1f}`\n\n🔍 **Analysis:**\n{detail_text}\n\n⏰ Timeframe: 15M")

def main_menu():
    markup = InlineKeyboardMarkup(row_width=2)
    markup.add(
        InlineKeyboardButton("EUR/USD", callback_data="sig_EUR/USD"),
        InlineKeyboardButton("GBP/USD", callback_data="sig_GBP/USD"),
        InlineKeyboardButton("USD/JPY", callback_data="sig_USD/JPY"),
        InlineKeyboardButton("GOLD", callback_data="sig_GOLD"),
        InlineKeyboardButton("NEXT SIGNAL", callback_data="next"),
    )
    return markup

@bot.message_handler(commands=['start'])
def start(message):
    bot.send_message(message.chat.id, "Welcome to Ism154 Forex Bot PRO!\n\n5 Indicators: RSI + MACD + EMA + Bollinger + Stochastic\nSelect a pair:", reply_markup=main_menu())

@bot.callback_query_handler(func=lambda call: True)
def handle(call):
    if call.data == "next":
        bot.send_message(call.message.chat.id, "Choose a pair:", reply_markup=main_menu())
        return
    if call.data.startswith("sig_"):
        pair = call.data.replace("sig_", "")
        bot.send_message(call.message.chat.id, "Analyzing 5 indicators...")
        text = make_signal(pair, PAIRS[pair])
        bot.send_message(call.message.chat.id, text, parse_mode="Markdown", reply_markup=main_menu())

def run_bot():
    print("Bot started...")
    bot.infinity_polling()

if __name__ == "__main__":
    threading.Thread(target=run_bot, daemon=True).start()
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
