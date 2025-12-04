from flask import Flask, request, jsonify
import requests
import os

app = Flask(__name__)

# -------------------------------
# SECURITY TOKEN
# -------------------------------
SECRET_TOKEN = "Vickybot@123"

TELEGRAM_BOT_TOKEN = "6574679913:AAEiUSOAoAArSvVaZ09Mc8uaisJHJN2JKHo"
TELEGRAM_CHAT_ID = "-1002313311833"

# Allowed scan names
ALLOWED_SCANS = [
    "15 min MACD CROSSOVER",
    "vicky bullish scans"
]

# ChartInk Scan Links
SCAN_LINKS = {
    "15 min MACD CROSSOVER": "https://chartink.com/screener/15-min-macd-crossover-74",
    "vicky bullish scans": "https://chartink.com/screener/vicky-bullish-scans-3"
}


def send_telegram_message(text):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": text,
        "parse_mode": "Markdown",
        "disable_web_page_preview": True   # <── Hides big preview card
    }
    requests.get(url, params=payload)


@app.route("/chartink", methods=["POST"])
def chartink_webhook():

    # -------------------------------
    # TOKEN VALIDATION
    # -------------------------------
    token = request.args.get("token")
    if token != SECRET_TOKEN:
        send_telegram_message(
            "❌ *Unauthorized Request*\n"
            "Invalid token used.\n"
            "Please contact the admin."
        )
        return jsonify({
            "error": "Unauthorized. Please contact the admin to access the webhook backend service."
        }), 403

    data = request.json
    print(data)

    # Extract scan name
    scan_name = data.get("scan_name", "").strip()

    # -------------------------------
    # SCAN NAME VALIDATION
    # -------------------------------
    if scan_name not in ALLOWED_SCANS:

        unauth_msg = (
            f"❌ *Unauthorized Alert Detected*\n\n"
            f"🔍 *Scan Name:* {scan_name}\n"
            "⚠️ This scan is not authorized to access the webhook backend service.\n"
            "Please contact the admin."
        )

        send_telegram_message(unauth_msg)

        return jsonify({
            "error": "Unauthorized. Please contact the admin to access the webhook backend service."
        }), 403
    # -------------------------------

    # Extract values
    stocks = data.get("stocks", "")
    prices = data.get("trigger_prices", "")
    time = data.get("triggered_at", "")

    # Lists
    stock_list = [s.strip() for s in stocks.split(",")]
    price_list = [p.strip() for p in prices.split(",")]

    stock_lines = [
        f"{idx}. *{s}* — ₹{p}"
        for idx, (s, p) in enumerate(zip(stock_list, price_list), start=1)
    ]
    stock_block = "\n".join(stock_lines)

    # Get the correct scan link
    scan_link = SCAN_LINKS.get(scan_name, "https://chartink.com")

    # Telegram message content with short icon-style link
    message = (
        f"📢 *ChartInk Alert Triggered*\n\n"
        f"📄 *Scan:* {scan_name}\n"
        f"🔗 [Open Scan]({scan_link})\n"    # Short clickable icon link
        f"⏰ *Time:* {time}\n\n"
        f"📊 *Triggered Stocks*\n"
        f"{stock_block}\n\n"
        f"🔎 More details available inside ChartInk."
    )

    send_telegram_message(message)

    return jsonify({"status": "success", "received": data})


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)
