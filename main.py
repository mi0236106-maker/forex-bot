import os, time, threading, io
import yfinance as yf
import pandas as pd
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import telebot
from flask import Flask

TOKEN = os.environ.get("BOT_TOKEN")
bot = telebot.TeleBot(TOKEN)
app = Flask(__name__)

@app.route('/')
def home():
    return "Ism154 Bot Live - 5 Indicators - 80 Sec"

PAIRS = ["GBP/JPY", "CAD/JPY", "EUR/USD", "USD/JPY", "EUR/JPY", "EUR/AUD"]
YF = {"GBP/JPY":"GBPJPY=X", "CAD/JPY":"CADJPY=X", "EUR/USD":"EURUSD=X", "USD/JPY":"USDJPY=X", "EUR/JPY":"EURJPY=X", "EUR/AUD":"EURAUD=X"}

alarm_on = True
pair_index = 0

def get_signal(pair):
    try:
        df = yf.download(YF[pair], period="1d", interval="1m", progress=False)
        if df.empty or len(df) < 30:
            return None, None, ""
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        close = df['Close']
        high = df['High']
        low = df['Low']

        # 1. RSI 14
        delta = close.diff()
        gain = delta.where(delta>0,0).rolling(14).mean()
        loss = -delta.where(delta<0,0).rolling(14).mean()
        rsi = 100 - (100/(1+(gain/loss)))
        last_rsi = float(rsi.iloc[-1])
        rsi_vote = 1 if last_rsi < 45 else -1 if last_rsi > 55 else 0
        rsi_txt = "Bearish" if last_rsi>55 else "Bullish" if last_rsi<45 else "Neutral"

        # 2. EMA 9 / 21
        ema9 = close.ewm(span=9).mean()
        ema21 = close.ewm(span=21).mean()
        ema_vote = 1 if float(close.iloc[-1]) > float(ema9.iloc[-1]) else -1
        ema_txt = "Uptrend -> BUY" if ema_vote==1 else "Downtrend -> SELL"

        # 3. MACD 12,26,9
        ema12 = close.ewm(span=12).mean()
        ema26 = close.ewm(span=26).mean()
        macd = ema12 - ema26
        signal_line = macd.ewm(span=9).mean()
        macd_vote = 1 if float(macd.iloc[-1]) > float(signal_line.iloc[-1]) else -1
        macd_txt = "Bullish -> BUY" if macd_vote==1 else "Bearish -> SELL"

        # 4. Bollinger 20, 2
        sma20 = close.rolling(20).mean()
        std20 = close.rolling(20).std()
        upper = sma20 + (std20*2)
        lower = sma20 - (std20*2)
        last_close = float(close.iloc[-1])
        if last_close <= float(lower.iloc[-1]):
            bb_vote = 1; bb_txt = "Lower -> BUY"
        elif last_close >= float(upper.iloc[-1]):
            bb_vote = -1; bb_txt = "Upper -> SELL"
        else:
            bb_vote = 0; bb_txt = "Middle"
        
        # 5. Stochastic 14,3
        lowest = low.rolling(14).min()
        highest = high.rolling(14).max()
        stoch = 100 * (close - lowest) / (highest - lowest)
        last_stoch = float(stoch.iloc[-1])
        if last_stoch < 20:
            stoch_vote = 1; stoch_txt = "Oversold -> BUY"
        elif last_stoch > 80:
            stoch_vote = -1; stoch_txt = "Overbought -> SELL"
        else:
            stoch_vote = 0; stoch_txt = "Neutral"

        # VOTING - ALL 5 INDICATORS
        total = rsi_vote + ema_vote + macd_vote + bb_vote + stoch_vote
        sig = "UP" if total >= 0 else "DOWN"

        detail = f"🔍 Analysis:\n• RSI: {rsi_txt} ({last_rsi:.0f})\n• EMA: {ema_txt}\n• MACD: {macd_txt}\n• Bollinger: {bb_txt}\n• Stoch: {stoch_txt} ({last_stoch:.0f})"
        return sig, df, detail
    except Exception as e:
        print(e)
        return None, None, ""

def make_chart(df, pair):
    plt.figure(figsize=(6,3))
    plt.plot(df['Close'].tail(60).values, color='blue', linewidth=2)
    plt.title(f"{pair} - 1 MIN")
    plt.grid(True, alpha=0.3)
    plt.tight_layout()
    buf = io.BytesIO()
    plt.savefig(buf, format='png')
    plt.close()
    buf.seek(0)
    return buf

def auto_loop():
    global pair_index
    while True:
        if not alarm_on:
            time.sleep(2)
            continue
        pair = PAIRS[pair_index % len(PAIRS)]
        pair_index += 1
        sig, df, detail = get_signal(pair)
        if sig and df is not None:
            try:
                with open("chat.txt") as f:
                    cid = f.read().strip()
                # 20 SEC - ALARM / PAIR
                caption1 = f"📊📊📊\n\n✔️ {pair}\n\n⏰ TIME : 1 MIN\n\n⏳ 20 SECONDS LEFT - GET READY!"
                chart = make_chart(df, pair)
                bot.send_photo(cid, chart, caption=caption1)
                time.sleep(20)
                # 60 SEC - TRADE CANDLE
                emoji = "⬆️ UP" if sig=="UP" else "⬇️ DOWN"
                caption2 = f"✔️ {pair}\n\n{emoji}\n\n⏰ TIME : 1 MIN\n\n🟢 TRADE NOW! - 60 SEC CANDLE STARTED\n\n{detail}"
                bot.send_message(cid, caption2)
                time.sleep(60)
                # TOTAL 80 SEC -> NEXT PAIR
            except Exception as e:
                print("send error", e)
                time.sleep(5)

@bot.message_handler(commands=['start'])
def start(m):
    with open("chat.txt","w") as f:
        f.write(str(m.chat.id))
    markup = telebot.types.InlineKeyboardMarkup()
    markup.add(telebot.types.InlineKeyboardButton("🔔 ALARM ON", callback_data="on"),
               telebot.types.InlineKeyboardButton("🔕 ALARM OFF", callback_data="off"))
    bot.send_message(m.chat.id, "Ism154 Bot ON ✅\n5 Indicators - Kabir Style - 80 Sec\n20 Sec Alarm + 60 Sec Trade", reply_markup=markup)

@bot.callback_query_handler(func=lambda c: True)
def alarm_btn(c):
    global alarm_on
    alarm_on = True if c.data=="on" else False
    bot.answer_callback_query(c.id, "ALARM ON ✅" if alarm_on else "ALARM OFF 🔕")

threading.Thread(target=auto_loop, daemon=True).start()
threading.Thread(target=lambda: bot.infinity_polling(), daemon=True).start()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT",10000)))
