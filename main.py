import os, threading, time, datetime
import yfinance as yf
import pandas as pd
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
    "USD/JPY": "USDJPY=X",
    "EUR/JPY": "EURJPY=X",
    "EUR/AUD": "EURAUD=X",
}

alert_on = set()

def analyze(symbol):
    try:
        df = yf.download(symbol, period="1d", interval="1m", progress=False)
        if df.empty or len(df) < 50:
            return None
        close = df['Close'].flatten()
        delta = close.diff()
        gain = delta.where(delta > 0, 0).rolling(14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
        rsi = 100 - (100 / (1 + (gain/loss)))
        ema20 = close.ewm(span=20).mean()
        ema50 = close.ewm(span=50).mean()
        ema12 = close.ewm(span=12).mean()
        ema26 = close.ewm(span=26).mean()
        macd = ema12 - ema26
        sig_line = macd.ewm(span=9).mean()
        sma20 = close.rolling(20).mean()
        std20 = close.rolling(20).std()
        upper = sma20 + (std20*2)
        lower = sma20 - (std20*2)
        low14 = close.rolling(14).min()
        high14 = close.rolling(14).max()
        stoch = 100 * (close - low14) / (high14 - low14)

        price = float(close.iloc[-1]); r = float(rsi.iloc[-1])
        e20 = float(ema20.iloc[-1]); e50 = float(ema50.iloc[-1])
        m = float(macd.iloc[-1]); s = float(sig_line.iloc[-1])
        up = float(upper.iloc[-1]); lo = float(lower.iloc[-1]); st = float(stoch.iloc[-1])

        votes = 0
        details = []
        if r < 30: votes += 1; details.append("RSI: Oversold -> BUY")
        elif r > 70: votes -= 1; details.append("RSI: Overbought -> SELL")
        elif r < 50: votes += 0.5; details.append("RSI: Bullish")
        else: votes -= 0.5; details.append("RSI: Bearish")
        if price > e20 > e50: votes += 1; details.append("EMA: Uptrend -> BUY")
        elif price < e20 < e50: votes -= 1; details.append("EMA: Downtrend -> SELL")
        else: details.append("EMA: Sideways")
        if m > s: votes += 1; details.append("MACD: Bullish -> BUY")
        else: votes -= 1; details.append("MACD: Bearish -> SELL")
        if price <= lo: votes += 1; details.append("Bollinger: Lower Band -> BUY")
        elif price >= up: votes -= 1; details.append("Bollinger: Upper Band -> SELL")
        else: details.append("Bollinger: Middle")
        if st < 20: votes += 1; details.append("Stoch: Oversold -> BUY")
        elif st > 80: votes -= 1; details.append("Stoch: Overbought -> SELL")
        else: details.append("Stoch: Neutral")
        # Return all - but we will HIDE it by default
        return price, r, e20, e50, m, s, up, lo, st, votes, details
    except Exception as e:
        print(e)
        return None

def short_signal(pair, symbol):
    res = analyze(symbol)
    if res is None:
        return f"{pair} - ❌ No data"
    price, r, e20, e50, m, s, up, lo, st, votes, details = res
    if votes >= 3: return f"{pair} - 🟢 BUY ⬆️ UP"
    elif votes >= 1: return f"{pair} - 🟢 BUY ⬆️ UP"
    elif votes <= -3: return f"{pair} - 🔴 SELL ⬇️ DOWN"
    elif votes <= -1: return f"{pair} - 🔴 SELL ⬇️ DOWN"
    else: return f"{pair} - ⚪ WAIT"

def full_signal(pair, symbol):
    # This is HIDDEN - only shown when you tap Show Analysis
    res = analyze(symbol)
    if res is None:
        return f"❌ {pair}: No data"
    price, r, e20, e50, m, s, up, lo, st, votes, details = res
    if votes >= 1: sig = "BUY 🟢 UP ⬆️"
    elif votes <= -1: sig = "SELL 🔴 DOWN ⬇️"
    else: sig = "WAIT ⚪ NO TRADE"
    detail_text = "\n".join([f"• {d}" for d in details])
    return (f"🔍 **{pair} - HIDDEN ANALYSIS**\n"
            f"💰 Price: `{price:.5f}`\n🎯 Signal: **{sig}**\n⭐ Score: `{votes}/5`\n\n"
            f"📊 **Indicators (Hidden):**\nRSI: `{r:.1f}`\nEMA 20: `{e20:.5f}` | EMA 50: `{e50:.5f}`\nMACD: `{m:.5f}` | Signal: `{s:.5f}`\nBollinger: `{lo:.5f} - {up:.5f}`\nStochastic: `{st:.1f}`\n\n"
            f"🔍 **Analysis:**\n{detail_text}\n\n⏰ 1M")

def main_menu():
    markup = InlineKeyboardMarkup(row_width=2)
    markup.add(
        InlineKeyboardButton("EUR/USD", callback_data="sig_EUR/USD"),
        InlineKeyboardButton("USD/JPY", callback_data="sig_USD/JPY"),
        InlineKeyboardButton("EUR/JPY", callback_data="sig_EUR/JPY"),
        InlineKeyboardButton("EUR/AUD", callback_data="sig_EUR/AUD"),
        InlineKeyboardButton("🔔 ALARM ON", callback_data="alarm_on"),
        InlineKeyboardButton("🔕 ALARM OFF", callback_data="alarm_off"),
    )
    return markup

def alarm_menu():
    # Alarm buttons: Show Analysis for each pair - hidden until tapped
    markup = InlineKeyboardMarkup(row_width=2)
    markup.add(
        InlineKeyboardButton("🔍 EUR/USD Analysis", callback_data="detail_EUR/USD"),
        InlineKeyboardButton("🔍 USD/JPY Analysis", callback_data="detail_USD/JPY"),
        InlineKeyboardButton("🔍 EUR/JPY Analysis", callback_data="detail_EUR/JPY"),
        InlineKeyboardButton("🔍 EUR/AUD Analysis", callback_data="detail_EUR/AUD"),
    )
    return markup

@bot.message_handler(commands=['start'])
def start(message):
    bot.send_message(message.chat.id,
        "👋 **Ism154 - 1M ALARM**\n\nPairs: EUR/USD, USD/JPY, EUR/JPY, EUR/AUD\nAlarm shows ONLY BUY UP / SELL DOWN.\nAnalysis is hidden - tap 🔍 to see it.\nTap ALARM ON:",
        parse_mode="Markdown", reply_markup=main_menu())

@bot.callback_query_handler(func=lambda call: True)
def handle(call):
    cid = call.message.chat.id
    if call.data == "alarm_on":
        alert_on.add(cid)
        bot.send_message(cid, "🔔 **ALARM ON!**\nYou will get ONLY BUY UP / SELL DOWN.", parse_mode="Markdown")
        return
    if call.data == "alarm_off":
        alert_on.discard(cid)
        bot.send_message(cid, "🔕 Alarm OFF")
        return
    if call.data.startswith("detail_"):
        pair = call.data.replace("detail_", "")
        bot.send_message(cid, "⏳ Loading hidden analysis...")
        text = full_signal(pair, PAIRS[pair])
        bot.send_message(cid, text, parse_mode="Markdown")
        return
    if call.data.startswith("sig_"):
        pair = call.data.replace("sig_", "")
        # Normal tap also shows ONLY short signal - clean
        bot.send_message(cid, "⏳ Analyzing 1M...")
        text = short_signal(pair, PAIRS[pair])
        bot.send_message(cid, f"**{text}**\n⏰ 1M", parse_mode="Markdown", reply_markup=alarm_menu())

def alarm_loop():
    sent_minute = -1
    while True:
        now = datetime.datetime.now()
        if now.second == 40 and now.minute != sent_minute:
            sent_minute = now.minute
            lines = []
            for pair, sym in PAIRS.items():
                lines.append(short_signal(pair, sym))
            msg = "⏰ **20 SECONDS LEFT! NEXT CANDLE!**\n🕯️ **1M - TRADE NOW:**\n\n" + "\n".join(lines) + "\n\n👆 BUY = UP ⬆️ | SELL = DOWN ⬇️"
            for cid in list(alert_on):
                try:
                    bot.send_message(cid, msg, parse_mode="Markdown", reply_markup=alarm_menu())
                except Exception as e:
                    print(e)
        time.sleep(1)

def run_bot():
    bot.infinity_polling()

if __name__ == "__main__":
    threading.Thread(target=run_bot, daemon=True).start()
    threading.Thread(target=alarm_loop, daemon=True).start()
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
