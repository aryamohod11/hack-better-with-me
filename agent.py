"""
agent.py
LearnAgent: the actual "agentic" core. Everything Flask needs — intake,
planning, dashboard data, nudges, and the quiz feedback loop — lives here
so app.py stays a thin HTTP layer.
"""
import datetime

import groq_client
import storage

NUDGE_INACTIVITY_DAYS = 3
REMEDIAL_SCORE_THRESHOLD = 60
PUSHBACK_DAYS = 3  # how far later weeks slide when a remedial task is inserted


class LearnAgent:
    def __init__(self):
        self.state = storage.get_state()

    # ------------------------------------------------------------------
    # Persistence helpers
    # ------------------------------------------------------------------
    def _save(self):
        storage.save_state(self.state)
        return self.state

    def _touch_active(self):
        self.state["progress"]["last_active"] = datetime.date.today().isoformat()

    def _log_event(self, kind, detail=""):
        self.state.setdefault("events", []).append({
            "kind": kind,
            "detail": detail,
            "at": datetime.datetime.now().isoformat(timespec="seconds"),
        })
        self.state["events"] = self.state["events"][-50:]  # keep it small

    # ------------------------------------------------------------------
    # 1. Intake: goal -> structured intent -> plan
    # ------------------------------------------------------------------
    def parse_intent(self, goal_text):
        return groq_client.parse_intent(goal_text)

    def generate_plan(self, intent):
        return groq_client.generate_plan(intent)

    def onboard(self, goal_text):
        intent = self.parse_intent(goal_text)
        plan = self.generate_plan(intent)

        hours_planned = sum(
            t["est_hours"] for w in plan["weeks"] for t in w["tasks"]
        )

        self.state = storage.reset_state()
        self.state["onboarded"] = True
        self.state["mock_mode"] = groq_client.MOCK_MODE
        self.state["intent"] = intent
        self.state["plan"] = plan
        self.state["progress"]["hours_planned_total"] = round(hours_planned, 1)
        self._touch_active()
        self.state["progress"]["streak_days"] = 1
        self._log_event("onboarded", intent["goal_summary"])
        return self._save()

    # ------------------------------------------------------------------
    # 2. Dashboard data
    # ------------------------------------------------------------------
    def get_dashboard_data(self):
        state = self.state
        if not state.get("onboarded"):
            return None

        plan = state["plan"]
        all_tasks = [t for w in plan["weeks"] for t in w["tasks"]]
        total = len(all_tasks)
        done = sum(1 for t in all_tasks if t["done"])
        completion_pct = round(100 * done / total, 1) if total else 0.0

        current_week = self._current_week()

        return {
            "intent": state["intent"],
            "plan": plan,
            "progress": state["progress"],
            "completion_pct": completion_pct,
            "tasks_done": done,
            "tasks_total": total,
            "current_week_number": current_week["week_number"] if current_week else None,
            "mock_mode": state.get("mock_mode", groq_client.MOCK_MODE),
            "nudges": state.get("nudges", [])[-5:],
        }

    def _current_week(self):
        """First week that still has an incomplete task; else the last week."""
        weeks = self.state["plan"]["weeks"]
        for w in weeks:
            if any(not t["done"] for t in w["tasks"]):
                return w
        return weeks[-1] if weeks else None

    # ------------------------------------------------------------------
    # 3. Task completion (drives streak + hours spent)
    # ------------------------------------------------------------------
    def complete_task(self, task_id, mark_done=True):
        progress = self.state["progress"]
        found = None
        for w in self.state["plan"]["weeks"]:
            for t in w["tasks"]:
                if t["id"] == task_id:
                    found = t
                    break
            if found:
                break
        if not found:
            return self.state

        was_done = found["done"]
        found["done"] = mark_done

        if mark_done and not was_done:
            progress["completed_task_ids"].append(task_id)
            progress["hours_spent_total"] = round(
                progress["hours_spent_total"] + found["est_hours"], 1
            )
            self._bump_streak()
        elif not mark_done and was_done:
            if task_id in progress["completed_task_ids"]:
                progress["completed_task_ids"].remove(task_id)
            progress["hours_spent_total"] = round(
                max(0, progress["hours_spent_total"] - found["est_hours"]), 1
            )

        self._touch_active()
        self._log_event("task_toggled", f"{task_id} -> {mark_done}")
        return self._save()

    def _bump_streak(self):
        progress = self.state["progress"]
        last = progress.get("last_active")
        today = datetime.date.today()
        if last:
            last_date = datetime.date.fromisoformat(last)
            gap = (today - last_date).days
            if gap == 0:
                pass  # already active today, streak unchanged
            elif gap == 1:
                progress["streak_days"] += 1
            else:
                progress["streak_days"] = 1
        else:
            progress["streak_days"] = 1

    # ------------------------------------------------------------------
    # 4. Feedback loop: quiz score -> remedial task + delayed milestones
    # ------------------------------------------------------------------
    def submit_quiz(self, topic, score):
        score = max(0, min(100, float(score)))
        current_week = self._current_week()
        if current_week is None:
            return self.state, False

        self.state["progress"]["quiz_history"].append({
            "topic": topic,
            "score": score,
            "week_number": current_week["week_number"],
            "at": datetime.datetime.now().isoformat(timespec="seconds"),
        })

        remediated = False
        if score < REMEDIAL_SCORE_THRESHOLD:
            remediated = True
            self._apply_remedial_change(current_week, topic)

        self._touch_active()
        self._log_event("quiz_submitted", f"{topic}: {score}")
        return self._save(), remediated

    def _apply_remedial_change(self, current_week, topic):
        """Insert a remedial task at the top of the current week, then push
        every later week's dates back by PUSHBACK_DAYS and tag them."""
        wn = current_week["week_number"]

        # Avoid stacking duplicate remedial tasks for the exact same topic.
        already = any(
            t.get("remedial") and topic.lower() in t["title"].lower()
            for t in current_week["tasks"]
        )
        if not already:
            remedial_task = {
                "id": f"w{wn}-remedial-{len(current_week['tasks']) + 1}",
                "title": f"Remedial review: {topic} (from checkpoint quiz)",
                "type": "study",
                "est_hours": 1.5,
                "done": False,
                "remedial": True,
            }
            current_week["tasks"].insert(0, remedial_task)
            self.state["progress"]["hours_planned_total"] = round(
                self.state["progress"]["hours_planned_total"] + remedial_task["est_hours"], 1
            )

        # Push back every week AFTER the current one.
        for w in self.state["plan"]["weeks"]:
            if w["week_number"] > wn:
                start = datetime.date.fromisoformat(w["start_date"]) + datetime.timedelta(days=PUSHBACK_DAYS)
                end = datetime.date.fromisoformat(w["end_date"]) + datetime.timedelta(days=PUSHBACK_DAYS)
                w["start_date"] = start.isoformat()
                w["end_date"] = end.isoformat()
                w["status"] = "pushed back"

    # ------------------------------------------------------------------
    # 5. Nudges
    # ------------------------------------------------------------------
    def check_for_nudge(self):
        """Real check based on wall-clock inactivity (used by a scheduler in
        production; the dashboard also exposes a manual simulate button for
        the demo since judging happens in one sitting)."""
        last = self.state["progress"].get("last_active")
        if not last:
            return None
        days = (datetime.date.today() - datetime.date.fromisoformat(last)).days
        if days >= NUDGE_INACTIVITY_DAYS:
            return self._generate_nudge(days)
        return None

    def simulate_inactivity(self, days=4):
        """Demo-only: back-date last_active so the nudge logic has something
        real to react to, then generate + store the nudge."""
        fake_last = datetime.date.today() - datetime.timedelta(days=days)
        self.state["progress"]["last_active"] = fake_last.isoformat()
        self._save()
        return self._generate_nudge(days)

    def _generate_nudge(self, days_inactive):
        intent = self.state.get("intent") or {}
        current_week = self._current_week()
        topic = current_week["title"] if current_week else intent.get("domain", "your plan")

        weak_topic = None
        quiz_history = self.state["progress"].get("quiz_history", [])
        low_scores = [q for q in quiz_history if q["score"] < REMEDIAL_SCORE_THRESHOLD]
        if low_scores:
            weak_topic = low_scores[-1]["topic"]

        context = {
            "domain": intent.get("domain", "your goal"),
            "topic": topic,
            "weak_topic": weak_topic,
            "days_inactive": days_inactive,
        }
        message = groq_client.generate_nudge(context)

        nudge = {
            "message": message,
            "reason": "inactivity" if not weak_topic else "inactivity+weak_topic",
            "at": datetime.datetime.now().isoformat(timespec="seconds"),
        }
        self.state.setdefault("nudges", []).append(nudge)
        self._save()
        return nudge

    # ------------------------------------------------------------------
    # 6. Reset
    # ------------------------------------------------------------------
    def reset(self):
        self.state = storage.reset_state()
        return self.state
