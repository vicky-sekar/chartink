from flask import Flask, request, jsonify
import requests
import os

app = Flask(__name__)

# ---------------------------------------------------
# 5PAISA OAUTH CALLBACK - RETURNS JSON ONLY
# ---------------------------------------------------
@app.route('/auth/callback', methods=['GET'])
def callback():
    # Extract RequestToken from redirect URL
    request_token = request.args.get('RequestToken')

    # If token missing
    if not request_token:
        return jsonify({
            "status": "error",
            "message": "RequestToken not found in URL"
        }), 400

    # Return token as JSON response
    return jsonify({
        "status": "success",
        "request_token": request_token
    }), 200


# ---------------------------------------------------
# SECURITY TOKEN FOR CHARTINK WEBHOOK
# ---------------------------------------------------
SECRET_TOKEN = "Vickybot@123"

TELEGRAM_BOT_TOKEN = "6574679913:AAEiUSOAoAArSvVaZ09Mc8uaisJHJN2JKHo"
TELEGRAM_CHAT_ID = "-1001960176951"

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
        "disable_web_page_preview": True
    }
    requests.get(url, params=payload)


# ---------------------------------------------------
# CHARTINK WEBHOOK ENDPOINT
# ---------------------------------------------------
@app.route("/chartink", methods=["POST"])
def chartink_webhook():

    # TOKEN VALIDATION
    token = request.args.get("token")
    if token != SECRET_TOKEN:
        send_telegram_message(
            "❌ *Unauthorized Request*\nInvalid token used.\nPlease contact the admin."
        )
        return jsonify({"error": "Unauthorized"}), 403

    data = request.json
    print(data)

    # Extract scan name
    scan_name = data.get("scan_name", "").strip()

    if scan_name not in ALLOWED_SCANS:
        unauth_msg = (
            f"❌ *Unauthorized Alert Detected*\n\n"
            f"🔍 *Scan:* {scan_name}\n"
            f"⚠️ This scan is not authorized.\n"
            f"Please contact the admin."
        )
        send_telegram_message(unauth_msg)
        return jsonify({"error": "Unauthorized"}), 403

    # Extract values
    stocks = data.get("stocks", "")
    prices = data.get("trigger_prices", "")
    time = data.get("triggered_at", "")

    stock_list = [s.strip() for s in stocks.split(",")]
    price_list = [p.strip() for p in prices.split(",")]

    stock_lines = []
    for idx, (s, p) in enumerate(zip(stock_list, price_list), start=1):
        try:
            price = int(float(p))
            sl = int(round(price * 0.98))
            target = int(round(price * 1.05))
        except:
            price = sl = target = 0

        stock_lines.append(
            f"{idx}. *{s}* — ₹{price}\n"
            f"   🎯 *Target:* ₹{target}\n"
            f"   🛑 *Stop Loss:* ₹{sl}"
        )

    stock_block = "\n".join(stock_lines)
    scan_link = SCAN_LINKS.get(scan_name, "https://chartink.com")

    message = (
        f"📢 *ChartInk Alert Triggered*\n\n"
        f"📄 *Scan:* {scan_name}\n"
        f"➡️ [Scan Link]({scan_link})\n"
        f"⏰ *Time:* {time}\n\n"
        f"📊 *Triggered Stocks*\n"
        f"{stock_block}"
    )

    send_telegram_message(message)

    return jsonify({"status": "success", "received": data})


# ---------------------------------------------------
# START SERVER
# ---------------------------------------------------
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)
