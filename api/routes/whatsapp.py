from flask import Blueprint, request, jsonify
from whatsapp_utils import handle_incoming_whatsapp

whatsapp_bp = Blueprint("whatsapp", __name__)

@whatsapp_bp.route("/webhook", methods=["POST"])
def whatsapp_webhook():
    data = request.form
    handle_incoming_whatsapp(data)
    return jsonify({"status": "received"})

@whatsapp_bp.route("/status", methods=["GET"])
def get_status():
    from utils.storage import load_json
    data = load_json("data/tasks.json")
    completed = sum(
        1 for g in data.get("goals", []) for t in g["plan"] if t.get("status") == "done"
    )
    total = sum(len(g["plan"]) for g in data.get("goals", []))
    return jsonify({"completed": completed, "total": total})
