"""
app.py
Thin Flask HTTP layer over LearnAgent. All logic lives in agent.py.
"""
import os

from dotenv import load_dotenv
load_dotenv()

from flask import Flask, jsonify, render_template, request

import groq_client
from agent import LearnAgent

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "dev-secret-change-me")


# --------------------------------------------------------------------------
# Pages
# --------------------------------------------------------------------------
@app.route("/")
def index():
    agent = LearnAgent()
    if agent.state.get("onboarded"):
        return render_template("dashboard.html", mock_mode=groq_client.MOCK_MODE)
    return render_template("index.html", mock_mode=groq_client.MOCK_MODE)


@app.route("/dashboard")
def dashboard():
    return render_template("dashboard.html", mock_mode=groq_client.MOCK_MODE)


# --------------------------------------------------------------------------
# API: intake
# --------------------------------------------------------------------------
@app.route("/api/intake", methods=["POST"])
def api_intake():
    data = request.get_json(force=True) or {}
    goal_text = (data.get("goal") or "").strip()
    if not goal_text:
        return jsonify({"error": "Please describe your learning goal."}), 400

    agent = LearnAgent()
    state = agent.onboard(goal_text)
    return jsonify({"ok": True, "dashboard": agent.get_dashboard_data()})


# --------------------------------------------------------------------------
# API: dashboard state
# --------------------------------------------------------------------------
@app.route("/api/state", methods=["GET"])
def api_state():
    agent = LearnAgent()
    dashboard_data = agent.get_dashboard_data()
    if dashboard_data is None:
        return jsonify({"onboarded": False})
    return jsonify({"onboarded": True, "dashboard": dashboard_data})


# --------------------------------------------------------------------------
# API: task completion
# --------------------------------------------------------------------------
@app.route("/api/task/complete", methods=["POST"])
def api_task_complete():
    data = request.get_json(force=True) or {}
    task_id = data.get("task_id")
    mark_done = bool(data.get("done", True))
    if not task_id:
        return jsonify({"error": "task_id is required"}), 400

    agent = LearnAgent()
    agent.complete_task(task_id, mark_done=mark_done)
    return jsonify({"ok": True, "dashboard": agent.get_dashboard_data()})


# --------------------------------------------------------------------------
# API: quiz submission (the feedback loop)
# --------------------------------------------------------------------------
@app.route("/api/quiz", methods=["POST"])
def api_quiz():
    data = request.get_json(force=True) or {}
    topic = (data.get("topic") or "").strip()
    score = data.get("score")
    if not topic or score is None:
        return jsonify({"error": "topic and score are required"}), 400
    try:
        score = float(score)
    except (TypeError, ValueError):
        return jsonify({"error": "score must be a number"}), 400

    agent = LearnAgent()
    state, remediated = agent.submit_quiz(topic, score)
    return jsonify({
        "ok": True,
        "remediated": remediated,
        "dashboard": agent.get_dashboard_data(),
    })


# --------------------------------------------------------------------------
# API: nudges
# --------------------------------------------------------------------------
@app.route("/api/nudge/check", methods=["GET"])
def api_nudge_check():
    agent = LearnAgent()
    nudge = agent.check_for_nudge()
    return jsonify({"nudge": nudge})


@app.route("/api/nudge/simulate", methods=["POST"])
def api_nudge_simulate():
    data = request.get_json(force=True) or {}
    days = int(data.get("days", 4))
    agent = LearnAgent()
    nudge = agent.simulate_inactivity(days=days)
    return jsonify({"nudge": nudge, "dashboard": agent.get_dashboard_data()})


# --------------------------------------------------------------------------
# API: reset
# --------------------------------------------------------------------------
@app.route("/api/reset", methods=["POST"])
def api_reset():
    agent = LearnAgent()
    agent.reset()
    return jsonify({"ok": True})


if __name__ == "__main__":
    debug = os.environ.get("FLASK_DEBUG", "1") == "1"
    app.run(host="0.0.0.0", port=5000, debug=debug)
