from flask import Flask, request, jsonify
import requests

app = Flask(__name__)

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

    stocks = data.get("stocks")
    prices = data.get("trigger_prices")
    time = data.get("triggered_at")
    scan_name = data.get("scan_name")

    message = f"Symbol: {stocks}\nPrice: {prices}\nTime: {time}\nScan: {scan_name}"

    send_telegram_message(message)

    return jsonify({"status": "success", "received": data})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)
