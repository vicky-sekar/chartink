from flask import Flask, request, jsonify
import requests
import os
import datetime

app = Flask(__name__)

# ---------------------------------------------------
# TIME FILTER FUNCTION
# ---------------------------------------------------
def is_allowed_time():
    now = datetime.datetime.now().time()

    # Window 1: 9:15 AM – 10:30 AM
    morning_start = datetime.time(9, 15)
    morning_end   = datetime.time(10, 30)

    # Window 2: 1:00 PM – 2:00 PM
    noon_start = datetime.time(13, 0)
    noon_end   = datetime.time(14, 0)

    return (morning_start <= now <= morning_end) or \
           (noon_start <= now <= noon_end)


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

    # ---------------------------------------------------
    # ⏰ TIME CHECK — BLOCK ALERT OUTSIDE ALLOWED WINDOWS
    # ---------------------------------------------------
    if not is_allowed_time():
        print("⛔ Alert ignored — outside allowed time window")
        return jsonify({"status": "ignored_outside_time"}), 200

    # CONTINUE WITH NORMAL LOGIC
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
