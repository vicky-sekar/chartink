from flask import Flask, request, jsonify
import requests
import os

app = Flask(__name__)

# ---------------------------------------------------
# IN-MEMORY TOKEN STORAGE (AUTO CLEARS ON RESTART)
# ---------------------------------------------------
SAVED_REQUEST_TOKEN = None


# ---------------------------------------------------
# 5PAISA OAUTH CALLBACK
# ---------------------------------------------------
@app.route('/auth/callback', methods=['GET'])
def callback():
    global SAVED_REQUEST_TOKEN

    request_token = request.args.get('RequestToken')
    all_params = request.args.to_dict()

    if not request_token:
        return jsonify({
            "status": "error",
            "message": "RequestToken not found in URL",
            "received_params": all_params
        }), 400

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
# TELEGRAM CONFIG
# ---------------------------------------------------
TELEGRAM_BOT_TOKEN = "6574679913:AAEiUSOAoAArSvVaZ09Mc8uaisJHJN2JKHo"

CHAT_ID_MAIN = "-1001960176951"      # BUY / SELL signals
CHAT_ID_DEFAULT = "-4891195470"      # All other scans


def send_telegram_message(text, chat_id):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "Markdown",
        "disable_web_page_preview": True
    }
    requests.get(url, params=payload)


# ---------------------------------------------------
# CHARTINK WEBHOOK (WITH SCAN NAME VALIDATION)
# ---------------------------------------------------
@app.route("/chartink", methods=["POST"])
def chartink_webhook():
    data = request.json
    print(data)

    stocks = data.get("stocks", "")
    prices = data.get("trigger_prices", "")
    time = data.get("triggered_at", "")
    scan_name = data.get("scan_name", "").strip()
    scan_lower = scan_name.lower()

    # ---------------------------------------------------
    # SELECT CHAT ID BASED ON SCAN NAME
    # ---------------------------------------------------
    if scan_lower in ["nifty_15min_buy", "nifty_15min_sell"]:
        chat_id = CHAT_ID_MAIN
    else:
        chat_id = CHAT_ID_DEFAULT

    stock_list = [s.strip() for s in stocks.split(",")]
    price_list = [p.strip() for p in prices.split(",")]

    stock_lines = []
    for idx, (s, p) in enumerate(zip(stock_list, price_list), start=1):

        try:
            price = float(p)
        except:
            price = 0

        # ---------------------------------------------------
        # SCAN-NAME BASED TARGET / SL LOGIC
        # ---------------------------------------------------
        if scan_lower == "nifty_15min_buy":
            target = round(price * 1.0045)
            sl = round(price * 0.9975)

        elif scan_lower == "nifty_15min_sell":
            target = round(price * 0.9955)
            sl = round(price * 1.0025)

        else:
            price = int(price)
            sl = int(round(price * 0.98))
            target = int(round(price * 1.05))

        stock_lines.append(
            f"{idx}. *{s}* — ₹{int(price)}\n"
            f"   🎯 *Target:* ₹{target}\n"
            f"   🛑 *Stop Loss:* ₹{sl}"
        )

    stock_block = "\n".join(stock_lines)

    # ---------------------------------------------------
    # SEND TO TELEGRAM
    # ---------------------------------------------------
    send_telegram_message(
        f"📢 *ChartInk Alert Triggered*\n\n"
        f"📄 *Scan:* {scan_name}\n"
        f"⏰ *Time:* {time}\n\n"
        f"{stock_block}",
        chat_id
    )

    return jsonify({"status": "success", "received": data})


# ---------------------------------------------------
# START SERVER
# ---------------------------------------------------
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)
