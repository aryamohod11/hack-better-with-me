"""
storage.py
Single-learner, file-based persistence. Swaps out for Postgres/Mongo later
without touching agent.py or app.py — every caller only knows about
get_state() / save_state() / reset_state().
"""
import json
import os
import threading

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
STATE_PATH = os.path.join(DATA_DIR, "state.json")

_lock = threading.Lock()

EMPTY_STATE = {
    "onboarded": False,
    "mock_mode": None,      # set on first run, informational only
    "intent": None,         # parsed goal brief
    "plan": None,           # week-by-week milestone plan
    "progress": {
        "streak_days": 0,
        "last_active": None,        # ISO date string
        "hours_planned_total": 0,
        "hours_spent_total": 0,
        "completed_task_ids": [],
        "quiz_history": [],         # [{topic, score, week_number, at}]
    },
    "nudges": [],            # [{message, at, reason}]
    "events": [],            # lightweight audit trail for the demo
}


def _ensure_dir():
    os.makedirs(DATA_DIR, exist_ok=True)


def get_state():
    """Return the current learner state, creating a fresh one if absent."""
    _ensure_dir()
    with _lock:
        if not os.path.exists(STATE_PATH):
            _write(EMPTY_STATE)
            return json.loads(json.dumps(EMPTY_STATE))
        with open(STATE_PATH, "r", encoding="utf-8") as f:
            try:
                return json.load(f)
            except json.JSONDecodeError:
                _write(EMPTY_STATE)
                return json.loads(json.dumps(EMPTY_STATE))


def save_state(state):
    _ensure_dir()
    with _lock:
        _write(state)
    return state


def reset_state():
    _ensure_dir()
    fresh = json.loads(json.dumps(EMPTY_STATE))
    with _lock:
        _write(fresh)
    return fresh


def _write(state):
    tmp_path = STATE_PATH + ".tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2, default=str)
    os.replace(tmp_path, STATE_PATH)
