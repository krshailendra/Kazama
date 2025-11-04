import os
from flask import Flask, request, jsonify
from flask_cors import CORS
from dotenv import load_dotenv
import json
from datetime import datetime

load_dotenv()

DATA_FILE = os.path.join("data", "status.json")

# Helper functions for local status update demo
def ensure_status_file():
    if not os.path.exists("data"):
        os.makedirs("data")
    if not os.path.exists(DATA_FILE):
        initial = {"updates": []}
        with open(DATA_FILE, "w", encoding="utf-8") as f:
            json.dump(initial, f, indent=2)

def update_status_log(msg, from_number, action=None):
    ensure_status_file()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open(DATA_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)
    event = {"msg": msg, "from": from_number, "action": action, "timestamp": now}
    data["updates"].append(event)
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)

app = Flask(__name__)
CORS(app)

@app.route("/whatsapp", methods=["POST"])
def whatsapp_webhook():
    """Receives WhatsApp messages via Twilio and updates local task status."""
    from_number = request.values.get("From", "")
    body = (request.values.get("Body", "") or "").strip().lower()
    print(f"Webhook received from {from_number}: {body}")
    action = None
    if "done" in body:
        action = "done"
    elif "remind" in body:
        action = "remind_later"
    else:
        action = "other"
    update_status_log(body, from_number, action)
    # You can update a shared JSON/db here to notify Streamlit
    resp_message = {
        "done": "✅ Marked as done! Your status will update in the app.",
        "remind_later": "⏰ I'll remind you later!",
        "other": "Reply with Mark as Done or Remind me."
    }
    from twilio.twiml.messaging_response import MessagingResponse
    resp = MessagingResponse()
    resp.message(resp_message.get(action, "OK"))
    return str(resp)

# Demo endpoint to debug/update status if needed
@app.route("/status", methods=["GET"])
def status_check():
    ensure_status_file()
    with open(DATA_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)
    return jsonify(data)

if __name__ == "__main__":
    ensure_status_file()
    app.run(host="0.0.0.0", port=5005, debug=True)
