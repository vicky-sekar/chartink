from flask import Flask, request, jsonify
import requests
import os

app = Flask(__name__)

# Your Telegram bot token and chat ID
TELEGRAM_BOT_TOKEN = "6574679913:AAEiUSOAoAArSvVaZ09Mc8uaisJHJN2JKHo"
TELEGRAM_CHAT_ID = "-1001960176951"

def send_telegram_message(text):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": text
    }
    requests.get(url, params=payload)

@app.route("/chartink", methods=["POST"])
def chartink_webhook():
    data = request.json

    # Extract ChartInk fields
    stocks = data.get("stocks", "")
    prices = data.get("trigger_prices", "")
    time = data.get("triggered_at", "")
    scan_name = data.get("scan_name", "")

    # Convert comma-separated string → list
    stock_list = [s.strip() for s in stocks.split(",")]
    price_list = [p.strip() for p in prices.split(",")]

    # Prepare multi-stock message
    message_lines = []
    for s, p in zip(stock_list, price_list):
        message_lines.append(f"{s} @ {p}")

    # Final Telegram message
    message = (
        f"Scan: {scan_name}\n"
        f"Time: {time}\n\n"
        f"Triggered Stocks:\n" +
        "\n".join(message_lines)
    )

    # Send to Telegram
    send_telegram_message(message)

    return jsonify({"status": "success", "received": data})

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)
