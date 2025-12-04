from flask import Flask, request, jsonify
import requests
import os

app = Flask(__name__)

TELEGRAM_BOT_TOKEN = "6574679913:AAEiUSOAoAArSvVaZ09Mc8uaisJHJN2JKHo"
TELEGRAM_CHAT_ID = "-1001960176951"

def send_telegram_message(text):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": text,
        "parse_mode": "Markdown"   # Enable bold, italics, etc.
    }
    requests.get(url, params=payload)

@app.route("/chartink", methods=["POST"])
def chartink_webhook():
    data = request.json

    # Extract values
    stocks = data.get("stocks", "")
    prices = data.get("trigger_prices", "")
    time = data.get("triggered_at", "")
    scan_name = data.get("scan_name", "")

    # Lists
    stock_list = [s.strip() for s in stocks.split(",")]
    price_list = [p.strip() for p in prices.split(",")]

    # Build stock list with numbering
    stock_lines = []
    for idx, (s, p) in enumerate(zip(stock_list, price_list), start=1):
        stock_lines.append(f"{idx}. *{s}* — ₹{p}")

    stock_block = "\n".join(stock_lines)

    # Final formatted Telegram message
    message = (
        f"📢 *ChartInk Alert Triggered*\n\n"
        f"📄 *Scan:* {scan_name}\n"
        f"⏰ *Time:* {time}\n\n"
        f"📊 *Triggered Stocks*\n"
        f"{stock_block}\n\n"
        f"🔎 More details inside ChartInk."
    )

    send_telegram_message(message)

    return jsonify({"status": "success", "received": data})

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)
