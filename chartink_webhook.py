import uuid
import time
import threading
import logging
from datetime import datetime, time as dtime
from zoneinfo import ZoneInfo

from flask import Flask, request, jsonify, render_template_string
import requests

app = Flask(__name__)

# ==================================================
# LOGGING
# ==================================================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s"
)
logger = logging.getLogger(__name__)

IST = ZoneInfo("Asia/Kolkata")

# ==================================================
# GLOBAL STORAGE
# ==================================================
SAVED_REQUEST_TOKEN = None
SAVED_ACCESS_TOKEN = None

OPEN_TRADES = {}
COMPLETED_TRADES = {}
FAILED_TRADES = {}

# uid -> True/False (thread running flag)
RUNNING_THREADS = {}

# ==================================================
# 5PAISA CONFIG
# ==================================================
BASE_URL = "https://Openapi.5paisa.com/VendorsAPI/Service1.svc"

APP_KEY = "qkr0d0BxUgqoZTnzVcwMtFurR1spsKnZ"
ENCRYPTION_KEY = "TjhBiSeSpoNUaOx1vYShRrbTrZTxRFYT"
USER_ID = "XmZprx70Hv1"
CLIENT_CODE = "52609055"

DEFAULT_SCRIP_CODE = 10576
DEFAULT_QTY = 200

# ==================================================
# TELEGRAM
# ==================================================
TELEGRAM_BOT_TOKEN = "6574679913:AAEiUSOAoAArSvVaZ09Mc8uaisJHJN2JKHo"
CHAT_ID_MAIN = "-1001960176951"
CHAT_ID_DEFAULT = "-4891195470"

# ==================================================
# HELPERS
# ==================================================
def headers():
    return {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {SAVED_ACCESS_TOKEN}"
    }


def send_telegram_message(text, chat_id):
    if not TELEGRAM_BOT_TOKEN or not chat_id:
        return
    try:
        requests.get(
            f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
            params={
                "chat_id": chat_id,
                "text": text,
                "parse_mode": "Markdown",
                "disable_web_page_preview": True
            },
            timeout=5
        )
    except Exception as e:
        logger.error(f"Telegram error: {e}")


# ==================================================
# AUTH
# ==================================================
@app.route("/auth/callback")
def auth_callback():
    global SAVED_REQUEST_TOKEN
    SAVED_REQUEST_TOKEN = request.args.get("RequestToken")
    logger.info("RequestToken saved")
    return jsonify({"request_token": SAVED_REQUEST_TOKEN})


@app.route("/get-request-token")
def get_request_token():
    if SAVED_REQUEST_TOKEN:
        return jsonify({"request_token": SAVED_REQUEST_TOKEN})
    return jsonify({"error": "No RequestToken"}), 404


@app.route("/get-access-token", methods=["POST"])
def get_access_token():
    global SAVED_ACCESS_TOKEN

    if not SAVED_REQUEST_TOKEN:
        return jsonify({"error": "RequestToken missing"}), 400

    if SAVED_ACCESS_TOKEN:
        return jsonify({"access_token": SAVED_ACCESS_TOKEN})

    payload = {
        "head": {"Key": APP_KEY},
        "body": {
            "RequestToken": SAVED_REQUEST_TOKEN,
            "EncryKey": ENCRYPTION_KEY,
            "UserId": USER_ID
        }
    }

    r = requests.post(f"{BASE_URL}/GetAccessToken", json=payload)
    SAVED_ACCESS_TOKEN = r.json()["body"]["AccessToken"]
    logger.info("AccessToken generated")
    return jsonify({"access_token": SAVED_ACCESS_TOKEN})


# ==================================================
# ORDER APIs
# ==================================================
def place_order(payload):
    return requests.post(
        f"{BASE_URL}/V1/PlaceOrderRequest",
        json=payload,
        headers=headers(),
        timeout=10
    ).json()


def get_order_status(remote_id):
    payload = {
        "head": {"key": APP_KEY},
        "body": {
            "ClientCode": CLIENT_CODE,
            "OrdStatusReqList": [{"Exch": "N", "RemoteOrderID": remote_id}]
        }
    }
    return requests.post(
        f"{BASE_URL}/V2/OrderStatus",
        json=payload,
        headers=headers(),
        timeout=10
    ).json()


def cancel_order(exch_id):
    payload = {"head": {"key": APP_KEY}, "body": {"ExchOrderID": exch_id}}
    return requests.post(
        f"{BASE_URL}/V1/CancelOrderRequest",
        json=payload,
        headers=headers(),
        timeout=10
    ).json()


# ==================================================
# PSEUDO BRACKET ENGINE (THREAD)
# ==================================================
def pseudo_bracket(uid, side, price):
    try:
        RUNNING_THREADS[uid] = True
        logger.info(f"Thread started for {uid}")

        entry_id = f"ENTRY_{uid}"
        sl_id = f"SL_{uid}"
        tgt_id = f"TGT_{uid}"

        OPEN_TRADES[uid]["status"] = "ENTRY_PLACED"

        # ENTRY ORDER
        place_order({
            "head": {"key": APP_KEY},
            "body": {
                "Exchange": "N",
                "ExchangeType": "C",
                "ScripCode": DEFAULT_SCRIP_CODE,
                "Price": 0,
                "OrderType": "Buy" if side == "BUY" else "Sell",
                "Qty": DEFAULT_QTY,
                "IsIntraday": True,
                "RemoteOrderID": entry_id
            }
        })

        # WAIT MAX 5 MIN
        start = time.time()
        filled = False

        while time.time() - start < 300 and RUNNING_THREADS.get(uid):
            s = get_order_status(entry_id)
            orders = s["body"].get("OrdStatusResLst", [])
            if orders and orders[0]["Status"] == "Fully Executed":
                filled = True
                break
            time.sleep(2)

        if not filled or not RUNNING_THREADS.get(uid):
            send_telegram_message(
                "⚠️ Entry not filled / thread stopped",
                CHAT_ID_MAIN
            )
            FAILED_TRADES[uid] = OPEN_TRADES.pop(uid)
            FAILED_TRADES[uid]["status"] = "ENTRY_NOT_FILLED"
            return

        target = OPEN_TRADES[uid]["target"]
        sl = OPEN_TRADES[uid]["sl"]

        # SL
        place_order({
            "head": {"key": APP_KEY},
            "body": {
                "Exchange": "N",
                "ExchangeType": "C",
                "ScripCode": DEFAULT_SCRIP_CODE,
                "Price": 0,
                "StopLossPrice": sl,
                "OrderType": "Sell" if side == "BUY" else "Buy",
                "Qty": DEFAULT_QTY,
                "IsIntraday": True,
                "RemoteOrderID": sl_id
            }
        })

        # TARGET
        place_order({
            "head": {"key": APP_KEY},
            "body": {
                "Exchange": "N",
                "ExchangeType": "C",
                "ScripCode": DEFAULT_SCRIP_CODE,
                "Price": target,
                "OrderType": "Sell" if side == "BUY" else "Buy",
                "Qty": DEFAULT_QTY,
                "IsIntraday": True,
                "RemoteOrderID": tgt_id
            }
        })

        # MONITOR
        while datetime.now(IST).time() < dtime(15, 10) and RUNNING_THREADS.get(uid):
            sl_s = get_order_status(sl_id)["body"].get("OrdStatusResLst", [])
            tgt_s = get_order_status(tgt_id)["body"].get("OrdStatusResLst", [])

            if sl_s and sl_s[0]["Status"] == "Fully Executed":
                cancel_order(tgt_s[0]["ExchOrderID"])
                OPEN_TRADES[uid]["status"] = "SL_HIT"
                COMPLETED_TRADES[uid] = OPEN_TRADES.pop(uid)
                return

            if tgt_s and tgt_s[0]["Status"] == "Fully Executed":
                cancel_order(sl_s[0]["ExchOrderID"])
                OPEN_TRADES[uid]["status"] = "TARGET_HIT"
                COMPLETED_TRADES[uid] = OPEN_TRADES.pop(uid)
                return

            time.sleep(2)

        OPEN_TRADES[uid]["status"] = "TIME_EXIT"
        COMPLETED_TRADES[uid] = OPEN_TRADES.pop(uid)

    except Exception as e:
        send_telegram_message("❌ Trade execution failed", CHAT_ID_MAIN)
        FAILED_TRADES[uid] = OPEN_TRADES.pop(uid, {})
        FAILED_TRADES[uid]["status"] = "FAILED"
        FAILED_TRADES[uid]["error"] = str(e)

    finally:
        RUNNING_THREADS.pop(uid, None)
        logger.info(f"Thread ended for {uid}")


# ==================================================
# CHARTINK WEBHOOK (UNCHANGED LOGIC)
# ==================================================
@app.route("/chartink", methods=["POST"])
def chartink_webhook():
    data = request.json or {}

    scan = data.get("scan_name", "").lower()
    price = float(data.get("trigger_prices", "0").split(",")[0])
    triggered_at = data.get("triggered_at", "")

    if scan not in ["nifty_15min_buy", "nifty_15min_sell"]:
        send_telegram_message("ping", CHAT_ID_DEFAULT)
        return jsonify({"status": "ping"})

    if datetime.now(IST).time() >= dtime(14, 30):
        send_telegram_message("⛔ No trade allowed after 2:30 PM", CHAT_ID_MAIN)
        return jsonify({"status": "failed", "reason": "after_2_30_pm"})

    if not SAVED_REQUEST_TOKEN or not SAVED_ACCESS_TOKEN:
        send_telegram_message("⚠️ RequestToken / AccessToken missing!", CHAT_ID_MAIN)
        return jsonify({"status": "failed", "reason": "token_missing"})

    side = "BUY" if scan == "nifty_15min_buy" else "SELL"

    if side == "BUY":
        target = round(price * 1.0045, 1)
        sl = round(price * 0.9975, 1)
    else:
        target = round(price * 0.9955, 1)
        sl = round(price * 1.0025, 1)

    uid = str(uuid.uuid4())[:8]

    OPEN_TRADES[uid] = {
        "scan": scan,
        "side": side,
        "price": price,
        "target": target,
        "sl": sl,
        "created": triggered_at,
        "status": "INIT"
    }

    send_telegram_message(
        f"📢 *ChartInk Alert*\n"
        f"Scan: {scan}\n"
        f"Side: {side}\n"
        f"Price: {price}\n"
        f"Target: {target}\n"
        f"SL: {sl}",
        CHAT_ID_MAIN
    )

    threading.Thread(
        target=pseudo_bracket,
        args=(uid, side, price),
        daemon=True
    ).start()

    return jsonify({"status": "started", "uid": uid})


# ==================================================
# MANUAL THREAD EXIT (ONLY THREAD)
# ==================================================
@app.route("/exit-thread/<uid>")
def exit_thread(uid):
    if uid in RUNNING_THREADS:
        RUNNING_THREADS[uid] = False
        return jsonify({"status": "thread_exit_requested", "uid": uid})
    return jsonify({"status": "no_running_thread"}), 404


# ==================================================
# DASHBOARD
# ==================================================
@app.route("/")
def dashboard():
    html = """
    <h1>📊 Trade Dashboard</h1>

    <h2>🟢 Open Trades</h2>
    <table border=1 cellpadding=6>
      <tr><th>UID</th><th>Side</th><th>Status</th><th>Target</th><th>SL</th><th>Created</th></tr>
      {% for k,v in open.items() %}
      <tr>
        <td>{{k}}</td><td>{{v.side}}</td><td>{{v.status}}</td>
        <td>{{v.target}}</td><td>{{v.sl}}</td><td>{{v.created}}</td>
      </tr>
      {% endfor %}
    </table>

    <h2>🟡 Completed Trades</h2>
    <table border=1 cellpadding=6>
      <tr><th>UID</th><th>Side</th><th>Status</th><th>Target</th><th>SL</th><th>Created</th></tr>
      {% for k,v in done.items() %}
      <tr>
        <td>{{k}}</td><td>{{v.side}}</td><td>{{v.status}}</td>
        <td>{{v.target}}</td><td>{{v.sl}}</td><td>{{v.created}}</td>
      </tr>
      {% endfor %}
    </table>

    <h2>🔴 Failed Trades</h2>
    <table border=1 cellpadding=6>
      <tr><th>UID</th><th>Side</th><th>Status</th><th>Target</th><th>SL</th><th>Created</th></tr>
      {% for k,v in failed.items() %}
      <tr>
        <td>{{k}}</td><td>{{v.side}}</td><td>{{v.status}}</td>
        <td>{{v.target}}</td><td>{{v.sl}}</td><td>{{v.created}}</td>
      </tr>
      {% endfor %}
    </table>

    <h2>🧵 Running Threads</h2>
    {% if threads %}
      <ul>
      {% for k in threads %}
        <li>{{k}} → <a href="/exit-thread/{{k}}">Stop Thread</a></li>
      {% endfor %}
      </ul>
    {% else %}
      <p>No running threads</p>
    {% endif %}
    """
    return render_template_string(
        html,
        open=OPEN_TRADES,
        done=COMPLETED_TRADES,
        failed=FAILED_TRADES,
        threads=RUNNING_THREADS.keys()
    )


# ==================================================
# RUN
# ==================================================
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080, debug=True)
