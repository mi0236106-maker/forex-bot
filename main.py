import os
import threading
from flask import Flask

app = Flask(__name__)

@app.route('/')
def home():
    return "Forex Bot is LIVE!"

def run_bot():
    print("Bot started...")

if __name__ == "__main__":
    threading.Thread(target=run_bot, daemon=True).start()
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
