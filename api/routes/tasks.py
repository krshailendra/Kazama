from flask import Blueprint, jsonify, request
from utils.storage import load_json, save_json
from whatsapp_utils import send_whatsapp_message

tasks_bp = Blueprint("tasks", __name__)

@tasks_bp.route("/", methods=["GET"])
def get_tasks():
    data = load_json("data/tasks.json")
    tasks = []
    for goal in data.get("goals", []):
        for t in goal.get("plan", []):
            tasks.append({
                "goal_id": goal["id"],
                "task": t["task"],
                "status": t.get("status", "pending")
            })
    return jsonify(tasks)

@tasks_bp.route("/complete", methods=["POST"])
def complete_task():
    payload = request.json
    goal_id = payload["goal_id"]
    task_name = payload["task"]

    data = load_json("data/tasks.json")
    for goal in data["goals"]:
        if goal["id"] == goal_id:
            for t in goal["plan"]:
                if t["task"] == task_name:
                    t["status"] = "done"

                    # Send WhatsApp confirmation (local Twilio sandbox)
                    send_whatsapp_message(f"✅ Task '{task_name}' marked complete!")
                    save_json("data/tasks.json", data)
                    return jsonify({"success": True})

    return jsonify({"success": False, "error": "Task not found"}), 404
