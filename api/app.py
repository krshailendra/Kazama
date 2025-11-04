from flask import Flask
from flask_cors import CORS

from routes.goals import goals_bp
from routes.tasks import tasks_bp
from routes.whatsapp import whatsapp_bp

app = Flask(__name__)
CORS(app)  # Allow local Expo app to connect

# Register routes
app.register_blueprint(goals_bp, url_prefix="/api/goals")
app.register_blueprint(tasks_bp, url_prefix="/api/tasks")
app.register_blueprint(whatsapp_bp, url_prefix="/api/whatsapp")

@app.route("/")
def index():
    return {"status": "API running", "message": "Welcome to Productivity API"}

if __name__ == "__main__":
    app.run(port=8000, debug=True)
