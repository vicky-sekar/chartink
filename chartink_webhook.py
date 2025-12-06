from flask import Flask, request, jsonify
import requests
import os

app = Flask(__name__)

# ---------------------------------------------------
# IN-MEMORY TOKEN STORAGE (AUTO CLEARS ON RESTART)
# ---------------------------------------------------
SAVED_REQUEST_TOKEN = None


# ---------------------------------------------------
# 5PAISA OAUTH CALLBACK - ALWAYS RETURNS CLEAN JSON
# ---------------------------------------------------
@app.route('/auth/callback', methods=['GET'])
def callback():
    global SAVED_REQUEST_TOKEN

    # Extract RequestToken from redirect URL
    request_token = request.args.get('RequestToken')
    all_params = request.args.to_dict()

    if not request_token:
        return jsonify({
            "status": "error",
            "message": "RequestToken not found in URL",
            "received_params": all_params
        }), 400

    # STORE TOKEN IN MEMORY
    SAVED_REQUEST_TOKEN = request_token

    return jsonify({
        "status": "success",
        "message": "Token received",
        "request_token": request_token
    }), 200


# ---------------------------------------------------
# ENDPOINT FOR LOCAL PYTHON TO FETCH TOKEN
# ---------------------------------------------------
@app.route("/get-request-token", methods=["GET"])
def get_request_token():
    global SAVED_REQUEST_TOKEN

    if not SAVED_REQUEST_TOKEN:
        return jsonify({"error": "No RequestToken received yet"}), 404

    return jsonify({"request_token": SAVED_REQUEST_TOKEN}), 200


# ---------------------------------------------------
# SECURITY TOKEN FOR CHARTINK WEBHOOK
# ---------------------------------------------------
SECRET_TOKEN = "Vickybot@123"

TELEGRAM_BOT_TOKEN = "6574679913:AAEiUSOAoAArSvVaZ09Mc8uaisJHJN2JKHo"
TELEGRAM_CHAT_ID = "-1001960176951"

ALLOWED_SCANS = [
    "15 min MACD CROSSOVER",
    "vicky bullish scans"
]

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
    token = request.args.get("token")
    if token != SECRET_TOKEN:
        send_telegram_message(
            "❌ *Unauthorized Request*\nInvalid token used.\nPlease contact the admin."
        )
        return jsonify({"error": "Unauthorized"}), 403

    data = request.json
    print(data)
    scan_name = data.get("scan_name", "").strip()

    if scan_name not in ALLOWED_SCANS:
        send_telegram_message(
            f"❌ *Unauthorized Alert*\nScan: {scan_name}"
        )
        return jsonify({"error": "Unauthorized"}), 403

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
    scan_link = SCAN_LINKS.get(scan_name, "#")

    send_telegram_message(
        f"📢 *ChartInk Alert Triggered*\n\n"
        f"📄 *Scan:* {scan_name}\n"
        f"➡️ [{scan_link}]({scan_link})\n"
        f"⏰ *Time:* {time}\n\n"
        f"{stock_block}"
    )

    return jsonify({"status": "success", "received": data})


# ---------------------------------------------------
# START SERVER
# ---------------------------------------------------
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)
