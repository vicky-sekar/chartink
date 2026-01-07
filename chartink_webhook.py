import uuid
import time
import threading
import logging
from datetime import datetime, time as dtime
from zoneinfo import ZoneInfo

from flask import Flask, request, jsonify, render_template_string
import requests
import traceback

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
RUNNING_THREADS = {}   # uid -> True/False

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
# PSEUDO BRACKET ENGINE
# ==================================================
def pseudo_bracket(uid):
    try:
        RUNNING_THREADS[uid] = True

        trade = OPEN_TRADES[uid]
        side = trade["side"]
        price = trade["price"]

        entry_id = f"ENTRY_{uid}"
        sl_id = f"SL_{uid}"
        tgt_id = f"TGT_{uid}"

        trade["status"] = "ENTRY_PLACED"

        # ENTRY
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

        # WAIT FOR ENTRY (5 min)
        start = time.time()
        while time.time() - start < 300 and RUNNING_THREADS.get(uid):
            s = get_order_status(entry_id)
            orders = s["body"].get("OrdStatusResLst", [])
            if orders and orders[0]["Status"] == "Fully Executed":
                break
            time.sleep(2)
        else:
            send_telegram_message("⚠️ Entry not filled", CHAT_ID_MAIN)
            FAILED_TRADES[uid] = OPEN_TRADES.pop(uid)
            FAILED_TRADES[uid]["status"] = "ENTRY_NOT_FILLED"
            return

        # SL & TARGET
        place_order({
            "head": {"key": APP_KEY},
            "body": {
                "Exchange": "N",
                "ExchangeType": "C",
                "ScripCode": DEFAULT_SCRIP_CODE,
                "Price": 0,
                "StopLossPrice": trade["sl"],
                "OrderType": "Sell" if side == "BUY" else "Buy",
                "Qty": DEFAULT_QTY,
                "IsIntraday": True,
                "RemoteOrderID": sl_id
            }
        })

        place_order({
            "head": {"key": APP_KEY},
            "body": {
                "Exchange": "N",
                "ExchangeType": "C",
                "ScripCode": DEFAULT_SCRIP_CODE,
                "Price": trade["target"],
                "OrderType": "Sell" if side == "BUY" else "Buy",
                "Qty": DEFAULT_QTY,
                "IsIntraday": True,
                "RemoteOrderID": tgt_id
            }
        })

        # BEFORE 3:10 PM
        while datetime.now(IST).time() < dtime(15, 10) and RUNNING_THREADS.get(uid):
            sl_s = get_order_status(sl_id)["body"].get("OrdStatusResLst", [])
            tgt_s = get_order_status(tgt_id)["body"].get("OrdStatusResLst", [])

            if sl_s and sl_s[0]["Status"] == "Fully Executed":
                cancel_order(tgt_s[0]["ExchOrderID"])
                trade["status"] = "SL_HIT"
                COMPLETED_TRADES[uid] = OPEN_TRADES.pop(uid)
                return

            if tgt_s and tgt_s[0]["Status"] == "Fully Executed":
                cancel_order(sl_s[0]["ExchOrderID"])
                trade["status"] = "TARGET_HIT"
                COMPLETED_TRADES[uid] = OPEN_TRADES.pop(uid)
                return

            time.sleep(2)

        # AFTER 3:10 PM → SQUARE OFF
        square_side = "Sell" if side == "BUY" else "Buy"

        place_order({
            "head": {"key": APP_KEY},
            "body": {
                "Exchange": "N",
                "ExchangeType": "C",
                "ScripCode": DEFAULT_SCRIP_CODE,
                "Price": 0,
                "OrderType": square_side,
                "Qty": DEFAULT_QTY,
                "IsIntraday": True,
                "RemoteOrderID": f"SQ_{uid}"
            }
        })

        trade["status"] = "TIME_SQUARE_OFF"
        COMPLETED_TRADES[uid] = OPEN_TRADES.pop(uid)

    except Exception as e:
        send_telegram_message("❌ Trade execution failed", CHAT_ID_MAIN)
        FAILED_TRADES[uid] = OPEN_TRADES.pop(uid, {})
        FAILED_TRADES[uid]["status"] = "FAILED"
        FAILED_TRADES[uid]["error"] = str(e)
    finally:
        RUNNING_THREADS.pop(uid, None)


# ==================================================
# CHARTINK WEBHOOK
# ==================================================
@app.route("/chartink", methods=["POST"])
def chartink_webhook():
    data = request.json or {}

    scan = data.get("scan_name", "").lower()
    triggered_at = data.get("triggered_at", "")

    prices = data.get("trigger_prices", "")
    price_list = [p.strip() for p in prices.split(",") if p.strip()]

    stocks = data.get("stocks", [])

    # 🔥 FIX 1: normalize stocks
    # string -> split by comma
    if isinstance(stocks, str):
        stocks = [s.strip() for s in stocks.split(",") if s.strip()]

    # list but contains single comma string
    elif isinstance(stocks, list) and len(stocks) == 1 and isinstance(stocks[0], str) and "," in stocks[0]:
        stocks = [s.strip() for s in stocks[0].split(",") if s.strip()]

    if scan in ["dummy"]:
        send_telegram_message("ping", CHAT_ID_DEFAULT)
        return jsonify({"status": "ping"})

    created_uids = []

    # -----------------------------
    # BUILD TELEGRAM MESSAGE
    # -----------------------------
    message_lines = [
        "📢 *ChartInk Alert*",
        f"Scan: {scan}",
        f"Time: {triggered_at}",
        ""
    ]

    for idx, stock in enumerate(stocks):
        try:
            # -----------------------------
            # SYMBOL HANDLING
            # -----------------------------
            if isinstance(stock, dict):
                nsecode = stock.get("nsecode", "").strip()
                name = stock.get("name", "").strip()
            else:
                nsecode = str(stock).strip()
                name = nsecode

            # -----------------------------
            # PRICE HANDLING
            # -----------------------------
            try:
                price = float(price_list[idx])
            except (IndexError, ValueError):
                price = 0.0

            uid = str(uuid.uuid4())[:8]

            OPEN_TRADES[uid] = {
                "scan": scan,
                "nsecode": nsecode,
                "name": name,
                "price": price,
                "created": triggered_at,
                "status": "INIT"
            }

            created_uids.append(uid)

            # add to telegram message
            message_lines.append(
                f"Symbol {idx + 1}: `{nsecode}`  Price: `{price}`"
            )

        except Exception as e:
            print("Processing error:", e)
            traceback.print_exc()
            continue

    # -----------------------------
    # SEND ONE TELEGRAM MESSAGE
    # -----------------------------
    send_telegram_message(
        "\n".join(message_lines),
        CHAT_ID_MAIN
    )

    return jsonify({
        "status": "started",
        "count": len(created_uids),
        "uids": created_uids
    })




# ==================================================
# MANUAL THREAD EXIT
# ==================================================
@app.route("/exit/<uid>")
def exit_thread(uid):
    RUNNING_THREADS[uid] = False
    send_telegram_message(f"🛑 Manual exit requested for {uid}", CHAT_ID_MAIN)
    return jsonify({"status": "exit_requested", "uid": uid})


# ==================================================
# DASHBOARD
# ==================================================
@app.route("/")
def dashboard():
    html = """
    <h1>📊 Trade Dashboard</h1>

    <h2>🟢 Open Trades / Alert Trades</h2>
    <table border=1 cellpadding=6>
      <tr><th>UID</th><th>symbol</th><th>scan</th><th>Created</th></tr>
      {% for k,v in open.items() %}
      <tr>
        <td>{{k}}</td><td>{{v.name}}</td><td>{{v.scan}}</td>
        <td>{{v.created}}</td>
      </tr>
      {% endfor %}
    </table>

    <h2>🧵 Running Threads</h2>
    <table border=1 cellpadding=6>
      <tr><th>UID</th><th>Action</th></tr>
      {% for k in threads %}
      <tr>
        <td>{{k}}</td>
        <td><a href="/exit/{{k}}">Exit</a></td>
      </tr>
      {% endfor %}
    </table>

    <h2>🟡 Completed Trades</h2>
    <table border=1 cellpadding=6>
      <tr><th>UID</th><th>Status</th></tr>
      {% for k,v in done.items() %}
      <tr><td>{{k}}</td><td>{{v.status}}</td></tr>
      {% endfor %}
    </table>

    <h2>🔴 Failed Trades</h2>
    <table border=1 cellpadding=6>
      <tr><th>UID</th><th>Status</th></tr>
      {% for k,v in failed.items() %}
      <tr><td>{{k}}</td><td>{{v.status}}</td></tr>
      {% endfor %}
    </table>
    """
    return render_template_string(
        html,
        open=OPEN_TRADES,
        done=COMPLETED_TRADES,
        failed=FAILED_TRADES,
        threads=RUNNING_THREADS.keys()
    )


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080, debug=True)
