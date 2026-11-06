import os
import threading
import time
import requests
import pandas as pd
import numpy as np
from datetime import datetime, timedelta, timezone
from flask import Flask
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton

TOKEN = os.environ.get("BOT_TOKEN")
bot = telebot.TeleBot(TOKEN)

app = Flask(__name__)
@app.route('/')
def home():
    return "Ism154 Forex Bot PRO - AUTO 1M LIVE!"

PAIRS = {
    "EUR/USD": "EURUSD=X",
    "GBP/USD": "GBPUSD=X",
    "USD/JPY": "USDJPY=X",
    "GOLD": "GC=F",
}

HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
auto_users = set()
YANGON = timezone(timedelta(hours=6, minutes=30))

def get_expiry():
    now = datetime.now(YANGON)
    expiry = now + timedelta(minutes=1)
    return now.strftime("%I:%M:%S %p"), expiry.strftime("%I:%M:%S %p")

def get_close(symbol):
    for host in ["query1.finance.yahoo.com", "query2.finance.yahoo.com"]:
        try:
            url = f"https://{host}/v8/finance/chart/{symbol}?range=1d&interval=1m"
            r = requests.get(url, headers=HEADERS, timeout=15)
            data = r.json()
            result = data['chart']['result'][0]
            closes = result['indicators']['quote'][0]['close']
            closes = [c for c in closes if c is not None]
            if len(closes) > 30:
                return pd.Series(closes)
        except Exception as e:
            print(f"Fail {host} {symbol}: {e}")
            continue
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
        return None, 0
    price, r, e20, e50, m, s, up, lo, st, votes, details = res
    entry_time, expiry_time = get_expiry()
    if votes >= 3: sig, emoji, action = "STRONG BUY 🟢🟢 CALL ⬆️⬆️", "🟢", "CALL ⬆️"
    elif votes >= 1: sig, emoji, action = "BUY 🟢 CALL ⬆️", "🟢", "CALL ⬆️"
    elif votes <= -3: sig, emoji, action = "STRONG SELL 🔴🔴 PUT ⬇️⬇️", "🔴", "PUT ⬇️"
    elif votes <= -1: sig, emoji, action = "SELL 🔴 PUT ⬇️", "🔴", "PUT ⬇️"
    else: sig, emoji, action = "WAIT ⚪ NEUTRAL - NO TRADE", "⚪", "NO TRADE"
    detail_text = "\n".join([f"• {d}" for d in details])
    text = (
        f"{emoji} **{pair_name} - 1M**\n"
        f"💰 Price: `{price:.5f}`\n"
        f"🎯 Signal: **{sig}**\n"
        f"⭐ Score: `{votes}/5`\n\n"
        f"⏰ **TRADE TIME (Myanmar):**\n"
        f"🕐 Entry: `{entry_time}`\n"
        f"⏳ Expiry: `{expiry_time}` (1 Min)\n"
        f"👉 Action: **{action}**\n\n"
        f"📊 **5 Indicators:**\n"
        f"RSI (14): `{r:.1f}`\n"
        f"EMA 20: `{e20:.5f}` | EMA 50: `{e50:.5f}`\n"
        f"MACD: `{m:.5f}` | Signal: `{s:.5f}`\n"
        f"Bollinger: `{lo:.5f} - {up:.5f}`\n"
        f"Stochastic: `{st:.1f}`\n\n"
        f"🔍 **Analysis:**\n{detail_text}\n\n"
        f"⏰ Timeframe: 1M | 🤖 AUTO"
    )
    return text, votes

def main_menu():
    markup = InlineKeyboardMarkup(row_width=2)
    markup.add(
        InlineKeyboardButton("EUR/USD", callback_data="sig_EUR/USD"),
        InlineKeyboardButton("GBP/USD", callback_data="sig_GBP/USD"),
        InlineKeyboardButton("USD/JPY", callback_data="sig_USD/JPY"),
        InlineKeyboardButton("GOLD", callback_data="sig_GOLD"),
        InlineKeyboardButton("🤖 AUTO ON - Every 1 Min", callback_data="auto_on"),
        InlineKeyboardButton("🛑 AUTO OFF", callback_data="auto_off"),
        InlineKeyboardButton("NEXT SIGNAL", callback_data="next"),
    )
    return markup

def auto_loop():
    print("AUTO loop started - Every 1 Min")
    while True:
        try:
            if len(auto_users) > 0:
                for pair_name, symbol in PAIRS.items():
                    text, votes = make_signal(pair_name, symbol)
                    if text is None:
                        continue
                    if votes >= 3 or votes <= -3:
                        for chat_id in list(auto_users):
                            try:
                                bot.send_message(chat_id, f"🤖 **AUTO SIGNAL - TAKE NOW!**\n\n{text}", parse_mode="Markdown", reply_markup=main_menu())
                            except Exception as e:
                                print(f"Auto send fail {chat_id}: {e}")
                    time.sleep(2)
            time.sleep(60)
        except Exception as e:
            print(f"Auto loop error: {e}")
            time.sleep(20)

@bot.message_handler(commands=['start'])
def start(message):
    bot.send_message(message.chat.id,
        "Welcome to Ism154 Forex Bot PRO! 🚀\n\n"
        "✅ Timeframe: 1M Scalping\n"
        "✅ 5 Indicators: RSI + MACD + EMA + Bollinger + Stochastic\n"
        "✅ Expiry: 1 Minute\n"
        "✅ Time: Myanmar Time\n"
        "✅ AUTO: STRONG signals every 1 Min\n\n"
        "Tap AUTO ON to start, or tap any pair for manual signal:",
        reply_markup=main_menu())

@bot.message_handler(commands=['auto'])
def auto_cmd(message):
    auto_users.add(message.chat.id)
    bot.send_message(message.chat.id, "🤖 AUTO ON! ✅\n\nI will send STRONG signals (Score 3+) every 1 Min with Entry + Expiry (1 Min).\n\nTap AUTO OFF to stop.", reply_markup=main_menu())

@bot.message_handler(commands=['stop'])
def stop_cmd(message):
    auto_users.discard(message.chat.id)
    bot.send_message(message.chat.id, "🛑 AUTO OFF. Stopped.", reply_markup=main_menu())

@bot.callback_query_handler(func=lambda call: True)
def handle(call):
    if call.data == "next":
        bot.send_message(call.message.chat.id, "Choose a pair:", reply_markup=main_menu())
        return
    if call.data == "auto_on":
        auto_users.add(call.message.chat.id)
        bot.send_message(call.message.chat.id, "🤖 AUTO ON! ✅\n\nSTRONG signals every 1 Min with 1 Min Expiry.\nOnly Score 3+ signals.\n\nTap AUTO OFF to stop.", reply_markup=main_menu())
        return
    if call.data == "auto_off":
        auto_users.discard(call.message.chat.id)
        bot.send_message(call.message.chat.id, "🛑 AUTO OFF. Stopped.", reply_markup=main_menu())
        return
    if call.data.startswith("sig_"):
        pair = call.data.replace("sig_", "")
        bot.send_message(call.message.chat.id, "Analyzing 5 indicators (1M)...")
        text, votes = make_signal(pair, PAIRS[pair])
        if text is None:
            text = f"❌ {pair}: Data not available, try again."
        bot.send_message(call.message.chat.id, text, parse_mode="Markdown", reply_markup=main_menu())

def run_bot():
    print("Bot started...")
    bot.infinity_polling()

if __name__ == "__main__":
    threading.Thread(target=run_bot, daemon=True).start()
    threading.Thread(target=auto_loop, daemon=True).start()
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
