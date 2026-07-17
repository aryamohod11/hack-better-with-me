# hack-better-with-me
<div align="center">

# LearnAgent

**An AI agent that reasons about the learner — not a catalogue that recommends content to them.**

Built for **Hack Better Than Me (HBTM)** · *Agentic AI for Human Potential* · IABTM × IIIT Pune

[![Python](https://img.shields.io/badge/Python-3.10+-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![Flask](https://img.shields.io/badge/Flask-3.0-000000?logo=flask&logoColor=white)](https://flask.palletsprojects.com/)
[![Groq](https://img.shields.io/badge/LLM-Groq%20%2F%20LLaMA%203.3-F55036?logo=groq&logoColor=white)](https://console.groq.com/)
[![License](https://img.shields.io/badge/license-MIT-8B8FA3)](#license)

[Setup](#setup) · [Demo Script](#demo-script-for-judging) · [How It Works](#how-it-works) · [Architecture](#architecture) · [API](#api-reference)

</div>

---

## The problem

Learners today have unlimited access to content — videos, courses, articles — and still fail to turn
that access into real outcomes: job-readiness, certifications, demonstrable skill. Most "personalized"
learning platforms are static content libraries with a recommendation layer bolted on. They don't
remember where a learner struggled, can't tell a learner on-track from one about to quit, and nudge
with generic reminders instead of anything actually useful.

## What LearnAgent does

LearnAgent is a closed-loop agent that sits with the learner through the whole journey, not just at
the start:

| # | Function | What it means in practice |
|---|---|---|
| 1 | **Understand Intent** | Parses a free-text goal into domain, skill level, target outcome, and a realistic timeline |
| 2 | **Plan Dynamically** | Generates a week-by-week, milestone-based plan |
| 3 | **Track Honestly** | Live completion %, streaks, time spent vs. planned |
| 4 | **Nudge Intelligently** | Detects inactivity or a failed quiz and intervenes with a message that references the *actual* goal and weak topic — never a generic reminder |
| 5 | **Learn From Feedback** | A low quiz score visibly rewrites the plan: inserts a remedial task and pushes later milestones back |

Step 5 feeds back into step 2 — the plan is never final. That loop is the whole point.

## Demo

> Screenshots go here once you've got the app running — drop a couple of PNGs in `docs/` and
> reference them like `![Dashboard](docs/dashboard.png)`.

## Setup

**Requirements:** Python 3.10+

```bash
git clone https://github.com/your-team/learnagent.git
cd learnagent
python -m venv venv
source venv/bin/activate       # Windows: venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
```

Get a free key at [console.groq.com](https://console.groq.com) and drop it into `.env`:

```env
GROQ_API_KEY=your_key_here
```

> **No key? No problem.** LearnAgent ships with a deterministic **mock mode** — if `GROQ_API_KEY`
> isn't set, every agent call falls back to offline logic instead of hitting the LLM. You'll see a
> "MOCK MODE" banner in the UI when it's active. This means the app is fully demoable with zero
> setup and zero dependency on a live network call during judging.

Run it:

```bash
python app.py
```

Open **http://localhost:5000**

## Demo script (for judging)

1. **Intake** — Enter a goal (e.g. *"Pass the AWS Solutions Architect exam"*). The agent parses
   domain, skill level, and timeline, then generates a week-by-week plan.
2. **Dashboard** — Point out the pulse strip (streak), completion %, and time spent vs. planned.
   Check off a task or two and watch the numbers move live.
3. **Feedback loop** *(the important one)* — In the "Checkpoint quiz" panel, submit a topic with a
   score under 60 (e.g. `VPC basics`, `40`). Watch the current week gain a remedial task at the top,
   and every later week get tagged **pushed back** with updated dates. This is the one thing a
   static course catalogue structurally cannot do.
4. **Nudges** — Click **"Simulate 4 days inactive"**. The agent generates a contextual message that
   names the actual goal and the weak/current topic — not "we miss you!"
5. **Reset** — "Start a new goal" clears state for the next run-through.

## How it works

```
Learner goal (free text)
        │
        ▼
  parse_intent()  ──▶  { domain, skill_level, target_outcome, timeline_weeks }
        │
        ▼
  generate_plan()  ──▶  week-by-week milestones + tasks
        │
        ▼
     Dashboard  ◀──────────────┐
        │                      │
        ▼                      │
  complete_task() / submit_quiz()
        │                      │
        ▼                      │
  score < 60?  ──yes──▶  insert remedial task, delay later weeks ──┘
        │
        no
        ▼
  plan continues as scheduled
```

Every LLM call goes through `groq_client.call_json()`, which asks for JSON-only output and falls
back to a mock response if no key is set or the call fails — so a flaky network never breaks a live
demo.

## Architecture

```
app.py          Flask routes — thin HTTP layer, no business logic
agent.py        LearnAgent core: intent parsing, planning, nudges, feedback loop
groq_client.py  Groq wrapper — JSON-mode prompting + offline mock fallback
storage.py      JSON file persistence (data/state.json)
templates/      index.html (goal intake), dashboard.html (main app)
static/
 ├─ css/style.css   design tokens (dark navy / amber / teal)
 └─ js/app.js       rendering + interactions, talks to the API below
```

**Why file-based storage?** This is a single-learner hackathon demo — a full database adds setup
risk without adding anything judges will see. `storage.py` is the only file that would need to
change to swap in Postgres/Mongo later; `agent.py` and `app.py` never touch the file system
directly.

## API reference

| Method | Route | Does |
|---|---|---|
| `GET` | `/` | Intake page, or dashboard if a plan already exists |
| `POST` | `/api/intake` | `{ goal }` → parses intent, generates plan, resets state |
| `GET` | `/api/state` | Returns the full current state as JSON |
| `POST` | `/api/task/<task_id>/complete` | Marks a task done, updates streak/progress |
| `POST` | `/api/quiz/submit` | `{ topic, score }` → triggers the feedback loop if `score < 60` |
| `POST` | `/api/nudge/check` | Checks real inactivity and generates a nudge if due |
| `POST` | `/api/nudge/simulate-inactivity` | Demo-only: backdates `last_active` to force a nudge |
| `POST` | `/api/reset` | Clears state for a new goal |

## Tech stack

- **Backend:** Python, Flask
- **LLM:** Groq (LLaMA 3.3 70B), JSON-mode prompting
- **Storage:** JSON file (`data/state.json`) — swappable
- **Frontend:** vanilla HTML/CSS/JS, no build step

## Roadmap

- [ ] Multi-user accounts (move off single-learner JSON storage, add auth)
- [ ] Spaced-repetition scheduling — decide *when* to resurface weak topics, not just what
- [ ] Real content integration — pull actual videos/articles/courses instead of task placeholders
- [ ] Mobile push nudges — move interventions from in-app to wherever the learner actually is

## Team

| Name | Role |
|---|---|
| — | Team Lead & AI/ML |
| — | Backend Engineering |
| — | Frontend & UX |
| — | Product & Research |

*B.Tech, RCOEM Nagpur*

## Contributing / team workflow

Standard flow: edit in VS Code → commit via GitHub Desktop → push. `data/` is gitignored so
nobody's local demo state clobbers anyone else's.

## License

MIT — built for HBTM 2026, free to reuse and extend.
