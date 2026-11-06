import os
import threading
import yfinance as yf
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

def analyze(symbol):
    try:
        df = yf.download(symbol, period="2d", interval="15m", progress=False)
        if df.empty or len(df) < 50:
            return None
        close = df['Close'].flatten()

        # 1. RSI (14)
        delta = close.diff()
        gain = delta.where(delta > 0, 0).rolling(14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
        rsi = 100 - (100 / (1 + (gain/loss)))

        # 2. EMA 20 & 50
        ema20 = close.ewm(span=20).mean()
        ema50 = close.ewm(span=50).mean()

        # 3. MACD
        ema12 = close.ewm(span=12).mean()
        ema26 = close.ewm(span=26).mean()
        macd = ema12 - ema26
        signal_line = macd.ewm(span=9).mean()

        # 4. Bollinger Bands (20, 2)
        sma20 = close.rolling(20).mean()
        std20 = close.rolling(20).std()
        upper = sma20 + (std20 * 2)
        lower = sma20 - (std20 * 2)

        # 5. Stochastic (14)
        low14 = close.rolling(14).min()
        high14 = close.rolling(14).max()
        stoch = 100 * (close - low14) / (high14 - low14)

        price = float(close.iloc[-1])
        r = float(rsi.iloc[-1])
        e20 = float(ema20.iloc[-1])
        e50 = float(ema50.iloc[-1])
        m = float(macd.iloc[-1])
        s = float(signal_line.iloc[-1])
        up = float(upper.iloc[-1])
        lo = float(lower.iloc[-1])
        st = float(stoch.iloc[-1])

        # VOTING SYSTEM
        votes = 0
        details = []

        # RSI vote
        if r < 30: votes += 1; details.append("RSI: Oversold -> BUY")
        elif r > 70: votes -= 1; details.append("RSI: Overbought -> SELL")
        elif r < 50: votes += 0.5; details.append("RSI: Bullish")
        else: votes -= 0.5; details.append("RSI: Bearish")

        # EMA vote
        if price > e20 > e50: votes += 1; details.append("EMA: Uptrend -> BUY")
        elif price < e20 < e50: votes -= 1; details.append("EMA: Downtrend -> SELL")
        else: details.append("EMA: Sideways")

        # MACD vote
        if m > s: votes += 1; details.append("MACD: Bullish -> BUY")
        else: votes -= 1; details.append("MACD: Bearish -> SELL")

        # Bollinger vote
        if price <= lo: votes += 1; details.append("Bollinger: At Lower Band -> BUY")
        elif price >= up: votes -= 1; details.append("Bollinger: At Upper Band -> SELL")
        else: details.append("Bollinger: Middle")

        # Stochastic vote
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
        return f"❌ {pair_name}: Data not available, try again."
    price, r, e20, e50, m, s, up, lo, st, votes, details = res

    if votes >= 3: sig, emoji = "STRONG BUY 🟢🟢 CALL ⬆️⬆️", "🟢"
    elif votes >= 1: sig, emoji = "BUY 🟢 CALL ⬆️", "🟢"
    elif votes <= -3: sig, emoji = "STRONG SELL 🔴🔴 PUT ⬇️⬇️", "🔴"
    elif votes <= -1: sig, emoji = "SELL 🔴 PUT ⬇️", "🔴"
    else: sig, emoji = "WAIT ⚪ NEUTRAL - NO TRADE", "⚪"

    detail_text = "\n".join([f"• {d}" for d in details])
    return (
        f"{emoji} **{pair_name}**\n"
        f"💰 Price: `{price:.5f}`\n"
        f"🎯 Signal: **{sig}**\n"
        f"⭐ Score: `{votes}/5`\n\n"
        f"📊 **Indicators:**\n"
        f"RSI (14): `{r:.1f}`\n"
        f"EMA 20: `{e20:.5f}` | EMA 50: `{e50:.5f}`\n"
        f"MACD: `{m:.5f}` | Signal: `{s:.5f}`\n"
        f"Bollinger: `{lo:.5f} - {up:.5f}`\n"
        f"Stochastic: `{st:.1f}`\n\n"
        f"🔍 **Analysis:**\n{detail_text}\n\n"
        f"⏰ Timeframe: 15M"
    )

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
    bot.send_message(message.chat.id,
        "Welcome to Ism154 Forex Bot PRO!\n\n5 Indicators: RSI + MACD + EMA + Bollinger + Stochastic\nSelect a pair:",
        reply_markup=main_menu())

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
