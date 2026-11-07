import os, time, threading, io
import yfinance as yf
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import telebot
from telebot.types import ReplyKeyboardMarkup, KeyboardButton, BotCommand
from flask import Flask

BOT_TOKEN = os.environ.get("BOT_TOKEN")
bot = telebot.TeleBot(BOT_TOKEN)
app = Flask(__name__)

@app.route('/')
def home():
    return "Bot Live"

alarm_on = True

def get_keyboard():
    kb = ReplyKeyboardMarkup(resize_keyboard=True, is_persistent=True)
    # SAME AS BEFORE - NOT CHANGED
    kb.row(KeyboardButton("🔔 ALARM ON"), KeyboardButton("🔕 ALARM OFF"))
    return kb

PAIRS = ["EUR/USD", "GBP/JPY", "EUR/JPY", "CAD/JPY", "AUD/JPY", "USD/JPY", "CHF/JPY"]
YF_MAP = {"EUR/USD":"EURUSD=X","GBP/JPY":"GBPJPY=X","EUR/JPY":"EURJPY=X","CAD/JPY":"CADJPY=X","AUD/JPY":"AUDJPY=X","USD/JPY":"USDJPY=X","CHF/JPY":"CHFJPY=X"}

def get_analysis(pair):
    try:
        df = yf.download(YF_MAP[pair], period="1d", interval="1m", progress=False)
        if df is None or len(df) < 60:
            return None
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        close = df['Close']
        delta = close.diff()
        gain = delta.where(delta>0,0).rolling(14).mean()
        loss = -delta.where(delta<0,0).rolling(14).mean()
        rsi = 100 - (100/(1+(gain/loss)))
        rsi_val = float(rsi.iloc[-1])
        ema9 = float(close.ewm(span=9).mean().iloc[-1])
        ema21 = float(close.ewm(span=21).mean().iloc[-1])
        ema_txt = "Uptrend -> BUY" if ema9 > ema21 else "Downtrend -> SELL"
        macd = close.ewm(span=12).mean() - close.ewm(span=26).mean()
        macd_sig = macd.ewm(span=9).mean()
        macd_txt = "Bullish -> BUY" if float(macd.iloc[-1]) > float(macd_sig.iloc[-1]) else "Bearish -> SELL"
        sma20 = close.rolling(20).mean()
        std20 = close.rolling(20).std()
        upper = float((sma20 + std20*2).iloc[-1])
        lower = float((sma20 - std20*2).iloc[-1])
        middle = float(sma20.iloc[-1])
        price = float(close.iloc[-1])
        if price > upper: boll_txt = "Upper -> SELL"
        elif price < lower: boll_txt = "Lower -> BUY"
        else: boll_txt = "Middle"
        low14 = float(df['Low'].rolling(14).min().iloc[-1])
        high14 = float(df['High'].rolling(14).max().iloc[-1])
        stoch_val = (price - low14)/(high14 - low14)*100 if high14!=low14 else 50
        if stoch_val > 80: stoch_txt = f"Overbought -> SELL ({stoch_val:.0f})"
        elif stoch_val < 20: stoch_txt = f"Oversold -> BUY ({stoch_val:.0f})"
        else: stoch_txt = f"Neutral ({stoch_val:.0f})"
        if rsi_val > 70: rsi_txt = f"Overbought -> SELL ({rsi_val:.0f})"
        elif rsi_val < 30: rsi_txt = f"Oversold -> BUY ({rsi_val:.0f})"
        elif rsi_val > 50: rsi_txt = f"Bearish ({rsi_val:.0f})"
        else: rsi_txt = f"Bullish ({rsi_val:.0f})"
        if pd.isna(rsi_val):
            rsi_txt = f"Neutral (nan)"
        if pd.isna(stoch_val):
            stoch_txt = f"Neutral (nan)"
        votes_buy = 0; votes_sell = 0
        if ema9 > ema21: votes_buy+=1
        else: votes_sell+=1
        if float(macd.iloc[-1]) > float(macd_sig.iloc[-1]): votes_buy+=1
        else: votes_sell+=1
        if price > middle: votes_buy+=1
        else: votes_sell+=1
        if rsi_val < 50: votes_buy+=1
        else: votes_sell+=1
        if stoch_val < 50: votes_buy+=1
        else: votes_sell+=1
        direction = "UP" if votes_buy > votes_sell else "DOWN"
        analysis = f"🔍 Analysis:\n• RSI: {rsi_txt}\n• EMA: {ema_txt}\n• MACD: {macd_txt}\n• Bollinger: {boll_txt}\n• Stoch: {stoch_txt}"
        return direction, analysis, df, price
    except Exception as e:
        print(f"Error {pair}: {e}")
        return None

def make_chart(df, pair):
    plt.figure(figsize=(8,4))
    plt.plot(df['Close'].tail(60), linewidth=2, color='blue')
    plt.title(f"{pair} - 1 MIN")
    plt.grid(True, alpha=0.3)
    buf = io.BytesIO()
    plt.savefig(buf, format='png')
    plt.close()
    buf.seek(0)
    return buf

@bot.message_handler(func=lambda m: m.text == "🔔 ALARM ON")
def alarm_on_func(m):
    global alarm_on
    alarm_on = True
    bot.send_message(m.chat.id, "🔔 Alarm ON ✅\nAlarm 20 sec before every trade.\nTrade 1 MIN | Wait 3 Min 40 Sec | Total 5 MIN", reply_markup=get_keyboard())

@bot.message_handler(func=lambda m: m.text == "🔕 ALARM OFF")
def alarm_off_func(m):
    global alarm_on
    alarm_on = False
    bot.send_message(m.chat.id, "🔕 Alarm OFF ❌\nNo more alarm. Signals paused.\nPress 🔔 ALARM ON to start again.", reply_markup=get_keyboard())

# --- ADDED ONLY - ALARM BOTTOM UNDER THE BOT - NOTHING ELSE CHANGED ---
@bot.message_handler(commands=['alarm'])
def alarm_cmd(m):
    global alarm_on
    alarm_on = True
    bot.send_message(m.chat.id, "🔔 Alarm ON ✅ via Bottom Menu\nAlarm 20 sec before every trade.\nTrade 1 MIN | Wait 3 Min 40 Sec | Total 5 MIN", reply_markup=get_keyboard())

@bot.message_handler(commands=['start'])
def start(m):
    global alarm_on
    if len(m.text.split()) > 1 and m.text.split()[1] == "alarm":
        alarm_on = True
        bot.send_message(m.chat.id, "🔔 Alarm ON ✅ via Menu Button", reply_markup=get_keyboard())
    else:
        bot.send_message(m.chat.id, "Ism154 Bot ON ✅\n5 Indicators - Kabir Style - 5 Min\n20 Sec Alarm + 60 Sec Trade + 3 Min 40 Sec Wait", reply_markup=get_keyboard())

def run_bot():
    chat_id_str = os.environ.get("CHAT_ID")
    if not chat_id_str:
        print("CHAT_ID missing")
        return
    chat_id = int(chat_id_str)
    idx = 0
    while True:
        if not alarm_on:
            time.sleep(10)
            continue
        pair = PAIRS[idx % len(PAIRS)]
        idx += 1
        try:
            result = get_analysis(pair)
            if not result: continue
            direction, analysis, df, price = result
            bot.send_message(chat_id, analysis, reply_markup=get_keyboard())
            chart = make_chart(df, pair)
            bot.send_photo(chat_id, chart, caption=f"✔️ {pair}\n\n⏰ TIME : 1 MIN\n\n⏳ 20 SECONDS LEFT - GET READY!", reply_markup=get_keyboard())
            time.sleep(20)
            if not alarm_on:
                bot.send_message(chat_id, "🔕 Alarm turned OFF - Trade skipped", reply_markup=get_keyboard())
                continue
            emoji = "⬆️ UP" if direction == "UP" else "⬇️ DOWN"
            bot.send_message(chat_id, f"✔️ {pair}\n\n{emoji}\n\n⏰ TIME : 1 MIN\n\n🟢 TRADE NOW! - 60 SEC CANDLE STARTED\n\n{analysis}", reply_markup=get_keyboard())
            time.sleep(60)
            bot.send_message(chat_id, f"⏳ {pair} Trade Finished. Wait 3 Min 40 Sec for next alarm...", reply_markup=get_keyboard())
            time.sleep(220)
        except Exception as e:
            print(f"Loop error: {e}")
            time.sleep(10)

# --- ADDED ONLY - SET BOTTOM MENU UNDER THE BOT - NOTHING ELSE CHANGED ---
try:
    bot.set_my_commands([
        BotCommand("start", "Start Bot"),
        BotCommand("alarm", "🔔 Alarm ON - Bottom Under Bot")
    ])
except:
    pass

threading.Thread(target=run_bot, daemon=True).start()
threading.Thread(target=lambda: bot.infinity_polling(skip_pending=True), daemon=True).start()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
