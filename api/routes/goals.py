from flask import Blueprint, request, jsonify
from utils.ml_interface import generate_plan
from utils.storage import load_json, save_json
import uuid, datetime

goals_bp = Blueprint("goals", __name__)

@goals_bp.route("/", methods=["GET"])
def get_goals():
    data = load_json("data/tasks.json")
    return jsonify(data.get("goals", []))

@goals_bp.route("/", methods=["POST"])
def create_goal():
    payload = request.json
    goal_text = payload.get("goal", "")
    duration = payload.get("duration", "")
    daily_hours = payload.get("daily_hours", "")
    mode = payload.get("mode", "")

    plan = generate_plan(goal_text, duration, daily_hours, mode)
    goal_id = str(uuid.uuid4())

    data = load_json("data/tasks.json")
    if "goals" not in data:
        data["goals"] = []

    data["goals"].append({
        "id": goal_id,
        "goal": goal_text,
        "plan": plan,
        "created_at": datetime.datetime.now().isoformat(),
        "completed": False
    })

    save_json("data/tasks.json", data)
    return jsonify({"id": goal_id, "plan": plan})
