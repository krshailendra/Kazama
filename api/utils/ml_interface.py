# Connects backend to your ML model logic (used in streamlit_app.py)
from main import generate_plan_with_grok  # or whatever function name you have

def generate_plan(goal, duration, daily_hours, mode):
    try:
        return generate_plan_with_grok(goal, duration, daily_hours, mode)
    except Exception as e:
        print("Error generating plan:", e)
        return []
