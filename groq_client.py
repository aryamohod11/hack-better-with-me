"""
groq_client.py
Thin wrapper around Groq's OpenAI-compatible chat completions endpoint.
If GROQ_API_KEY is unset, every function below returns deterministic mock
output instead — the app works fully offline for hackathon demos.
"""
import json
import os
import re
import datetime

import requests

GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "").strip()
GROQ_MODEL = os.environ.get("GROQ_MODEL", "llama-3.1-8b-instant")
GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"

MOCK_MODE = len(GROQ_API_KEY) == 0


def _call_groq(system_prompt, user_prompt, json_mode=True, max_tokens=1500):
    """Raw call to Groq. Raises on failure — callers should catch and
    fall back to mock logic so a flaky/missing key never breaks the demo."""
    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": GROQ_MODEL,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": 0.4,
        "max_tokens": max_tokens,
    }
    if json_mode:
        payload["response_format"] = {"type": "json_object"}

    resp = requests.post(GROQ_URL, headers=headers, json=payload, timeout=30)
    resp.raise_for_status()
    data = resp.json()
    content = data["choices"][0]["message"]["content"]
    return content


def _safe_json(text, fallback):
    try:
        cleaned = text.strip()
        cleaned = re.sub(r"^```(json)?", "", cleaned).strip()
        cleaned = re.sub(r"```$", "", cleaned).strip()
        return json.loads(cleaned)
    except Exception:
        return fallback


# --------------------------------------------------------------------------
# 1. Intent parsing
# --------------------------------------------------------------------------
INTENT_SYSTEM_PROMPT = """You are an intake agent for a personal learning coach.
Given a learner's free-text goal, extract a structured brief.
Respond ONLY with a JSON object, no preamble, no markdown fences, matching:
{
  "domain": string,                 // e.g. "Cloud Computing (AWS)"
  "level": "beginner"|"intermediate"|"advanced",
  "timeline_weeks": integer,        // learner's implied or stated deadline, 2-16
  "focus_areas": [string, ...],     // 3-6 concrete sub-topics
  "goal_summary": string            // one-sentence restatement of the goal
}"""


def parse_intent_llm(goal_text):
    content = _call_groq(INTENT_SYSTEM_PROMPT, goal_text)
    return _safe_json(content, None)


def parse_intent_mock(goal_text):
    text = goal_text.lower()

    domain_map = [
        (["aws", "solutions architect", "cloud"], "Cloud Computing (AWS)",
         ["IAM & security basics", "VPC & networking", "EC2 & compute", "S3 & storage", "Well-Architected Framework"]),
        (["python"], "Python Programming",
         ["Core syntax & data types", "Functions & modules", "OOP in Python", "File I/O & error handling", "Testing basics"]),
        (["data science", "machine learning", "ml ", "data analyst"], "Data Science & ML",
         ["Python for data analysis", "Statistics fundamentals", "Pandas & data wrangling", "Core ML algorithms", "Model evaluation"]),
        (["spanish", "french", "german", "language"], "Language Learning",
         ["Core vocabulary", "Grammar fundamentals", "Listening practice", "Speaking practice", "Conversational fluency"]),
        (["react", "frontend", "javascript", "web dev"], "Web Development",
         ["HTML/CSS fundamentals", "JavaScript core concepts", "React components & state", "APIs & data fetching", "Deployment basics"]),
        (["guitar", "piano", "music"], "Music Skill",
         ["Basic technique", "Reading notation/tabs", "Rhythm & timing", "Repertoire building", "Improvisation"]),
    ]

    domain, focus_areas = "General Skill Development", [
        "Foundational concepts", "Core practice", "Applied exercises", "Mock assessment", "Review & consolidation"
    ]
    for keywords, mapped_domain, areas in domain_map:
        if any(k in text for k in keywords):
            domain, focus_areas = mapped_domain, areas
            break

    if any(w in text for w in ["beginner", "new to", "from scratch", "never"]):
        level = "beginner"
    elif any(w in text for w in ["advanced", "expert", "master"]):
        level = "advanced"
    else:
        level = "intermediate"

    weeks_match = re.search(r"(\d+)\s*(week|wk)", text)
    months_match = re.search(r"(\d+)\s*(month|mo\b)", text)
    if weeks_match:
        timeline_weeks = max(2, min(16, int(weeks_match.group(1))))
    elif months_match:
        timeline_weeks = max(2, min(16, int(months_match.group(1)) * 4))
    else:
        timeline_weeks = 6

    return {
        "domain": domain,
        "level": level,
        "timeline_weeks": timeline_weeks,
        "focus_areas": focus_areas,
        "goal_summary": goal_text.strip().rstrip(".") + ".",
    }


def parse_intent(goal_text):
    if MOCK_MODE:
        return parse_intent_mock(goal_text)
    try:
        result = parse_intent_llm(goal_text)
        if not result or "domain" not in result:
            raise ValueError("malformed LLM intent response")
        result["timeline_weeks"] = max(2, min(16, int(result.get("timeline_weeks", 6))))
        return result
    except Exception:
        return parse_intent_mock(goal_text)


# --------------------------------------------------------------------------
# 2. Plan generation
# --------------------------------------------------------------------------
PLAN_SYSTEM_PROMPT = """You are a curriculum-planning agent. Given a structured
learner brief, produce a week-by-week milestone plan. Respond ONLY with JSON:
{
  "weeks": [
    {
      "week_number": integer,
      "title": string,
      "tasks": [
        {"title": string, "type": "study"|"practice"|"quiz", "est_hours": number}
      ]
    }
  ]
}
Each week must have 3-5 tasks and the LAST task of each week must be of
type "quiz" titled like "Checkpoint quiz: <topic>". Cover the focus_areas
across the weeks in a sensible progression matching the learner's level."""


def generate_plan_llm(intent):
    content = _call_groq(PLAN_SYSTEM_PROMPT, json.dumps(intent))
    return _safe_json(content, None)


def generate_plan_mock(intent):
    weeks_n = intent["timeline_weeks"]
    focus_areas = intent["focus_areas"] or ["Core topic"]
    weeks = []
    for i in range(weeks_n):
        topic = focus_areas[i % len(focus_areas)]
        week_num = i + 1
        tasks = [
            {"title": f"Study: {topic}", "type": "study", "est_hours": 2},
            {"title": f"Practice exercises: {topic}", "type": "practice", "est_hours": 1.5},
        ]
        if week_num % 2 == 0:
            tasks.append({"title": f"Review & notes: {topic}", "type": "study", "est_hours": 1})
        tasks.append({"title": f"Checkpoint quiz: {topic}", "type": "quiz", "est_hours": 0.5})
        weeks.append({
            "week_number": week_num,
            "title": f"Week {week_num}: {topic}",
            "tasks": tasks,
        })
    return {"weeks": weeks}


def generate_plan(intent):
    if MOCK_MODE:
        raw = generate_plan_mock(intent)
    else:
        try:
            raw = generate_plan_llm(intent)
            if not raw or "weeks" not in raw or not raw["weeks"]:
                raise ValueError("malformed LLM plan response")
        except Exception:
            raw = generate_plan_mock(intent)
    return _materialize_plan(raw)


def _materialize_plan(raw_plan):
    """Attach ids, dates, done flags, and status to a raw week/task skeleton."""
    today = datetime.date.today()
    weeks_out = []
    for w in raw_plan["weeks"]:
        wn = w["week_number"]
        start = today + datetime.timedelta(days=7 * (wn - 1))
        end = start + datetime.timedelta(days=6)
        tasks_out = []
        for ti, t in enumerate(w["tasks"]):
            tasks_out.append({
                "id": f"w{wn}t{ti+1}",
                "title": t["title"],
                "type": t.get("type", "study"),
                "est_hours": float(t.get("est_hours", 1)),
                "done": False,
                "remedial": False,
            })
        weeks_out.append({
            "week_number": wn,
            "title": w.get("title", f"Week {wn}"),
            "start_date": start.isoformat(),
            "end_date": end.isoformat(),
            "tasks": tasks_out,
            "status": "pending",
        })
    return {"weeks": weeks_out}


# --------------------------------------------------------------------------
# 3. Contextual nudges
# --------------------------------------------------------------------------
NUDGE_SYSTEM_PROMPT = """You are a warm, direct learning coach. Given context
about a learner who has gone quiet, write ONE short nudge message (2-3
sentences max) that references their actual goal and current/weak topic by
name. Be encouraging, not naggy. Respond ONLY with JSON: {"message": string}"""


def generate_nudge_llm(context):
    content = _call_groq(NUDGE_SYSTEM_PROMPT, json.dumps(context))
    result = _safe_json(content, None)
    return result.get("message") if result else None


def generate_nudge_mock(context):
    domain = context.get("domain", "your goal")
    topic = context.get("topic", "your current milestone")
    days = context.get("days_inactive", 4)
    weak = context.get("weak_topic")

    if weak:
        return (
            f"It's been {days} days — your {domain} plan is waiting, and "
            f"{weak} is still the sticking point from your last checkpoint quiz. "
            f"Even 20 minutes on it today keeps your streak alive and stops it "
            f"from snowballing into next week's material."
        )
    return (
        f"It's been {days} days since you touched your {domain} plan. "
        f"You were making progress on \"{topic}\" — a short 20-minute session "
        f"today is enough to keep momentum without falling behind schedule."
    )


def generate_nudge(context):
    if MOCK_MODE:
        return generate_nudge_mock(context)
    try:
        msg = generate_nudge_llm(context)
        if not msg:
            raise ValueError("empty nudge")
        return msg
    except Exception:
        return generate_nudge_mock(context)
