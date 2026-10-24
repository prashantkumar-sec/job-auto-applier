# agentverse_agent.py
# ----------------------------------------------------------------
# Job Auto Applier v2 - Agentverse HOSTED version (paste into the Agentverse editor)
#
# NEW in v2:
#   * Pre-Application Recruiter Simulation (3 personas, 3 parallel LLM calls)
#   * Application Tracker (status per application)
#   * Smart Follow-up Scheduler (Day 3 check-in, Day 7 value-add, Day 14 portfolio)
#
# Flow (all inside ASI:One chat, Agent Chat Protocol):
#   find python internships        -> live jobs from Remotive, with match score
#   apply 2 [from 1 Jan 2027]      -> recruiter simulation + email DRAFT
#   confirm [me@mail.com]          -> sends via Resend, logs in tracker, schedules follow-ups
#   cancel                         -> discards the draft
#   tracker                        -> all applications + next follow-up
#   update 2 interview             -> applied | interview | offer | rejected | withdrawn
#   followups                      -> check what is due now
#   send followup 2                -> send the ready follow-up for application #2
#   skip followup 2                -> skip the ready follow-up
#   fastforward 3                  -> DEMO ONLY: pretend 3 days passed
#
# Agentverse -> your agent -> Secrets:
#   RESEND_API_KEY      (resend.com, free tier)
#   APPLY_TO_EMAIL      (where emails go; on Resend free tier with onboarding@resend.dev
#                        this must be YOUR OWN email. Remotive has no recruiter emails,
#                        so the demo sends to you.)
#   ASI1_API_KEY        (asi1.ai, powers the recruiter personas. Without it the agent
#                        falls back to rule-based personas so the demo never dies)
#   APPLICANT_NAME      (optional, default "Prashant")
#   APPLICANT_SKILLS    (optional, comma separated)
#   APPLICANT_LINKS     (optional, e.g. "GitHub: https://github.com/...")
#   APPLICANT_PORTFOLIO (optional, used in the Day 14 follow-up)
#   APPLICANT_BIO       (optional, 1-3 lines: projects, achievements. Makes the simulation sharper)
#
# NOTE: Agentverse injects the `agent` object. Do NOT create Agent() or call run().
# ----------------------------------------------------------------

import json
import os
import re
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from uuid import uuid4 

import requests
from uagents import Context, Protocol
from uagents_core.contrib.protocols.chat import (
    ChatAcknowledgement,
    ChatMessage,
    TextContent,
    chat_protocol_spec,
)

# ==========================================
# 1. Config
# ==========================================

APPLICANT_NAME = os.getenv("APPLICANT_NAME", "Prashant")
SKILLS = [s.strip().lower() for s in os.getenv("APPLICANT_SKILLS", "python,next.js,react,sql,javascript").split(",") if s.strip()]
APPLICANT_LINKS = os.getenv("APPLICANT_LINKS", "")
APPLICANT_PORTFOLIO = os.getenv("APPLICANT_PORTFOLIO", "") or APPLICANT_LINKS
APPLICANT_BIO = os.getenv("APPLICANT_BIO", "B.Tech CSE student looking for an internship.")
APPLY_TO_EMAIL = os.getenv("APPLY_TO_EMAIL", "")
RESEND_API_KEY = os.getenv("RESEND_API_KEY", "")
ASI1_API_KEY = os.getenv("ASI1_API_KEY", "")

REMOTIVE_URL = "https://remotive.com/api/remote-jobs"
ASI1_URL = "https://api.asi1.ai/v1/chat/completions"
ASI1_MODEL = "asi1-mini"
HN_SEARCH_URL = "https://hn.algolia.com/api/v1/search"
HTTP_TIMEOUT = 10
LLM_TIMEOUT = 25

FOLLOWUP_DAYS = (3, 7, 14)
CLOSED_STATUSES = ("interview", "offer", "rejected", "withdrawn")
VALID_STATUSES = ("applied", "followed_up") + CLOSED_STATUSES

# Used only if the live API fails or only senior roles are found. Clearly labelled.
FALLBACK_JOBS = [
    {"title": "Python Developer Intern (sample)", "company": "DataSync", "url": "https://remotive.com/remote-jobs?search=python+intern", "tags": ["python", "sql"], "description": "python backend sql intern"},
    {"title": "Frontend React Intern (sample)", "company": "TechNova", "url": "https://remotive.com/remote-jobs?search=react+intern", "tags": ["react", "javascript"], "description": "react javascript frontend intern"},
    {"title": "Full Stack Intern (sample)", "company": "CloudForge", "url": "https://remotive.com/remote-jobs?search=full+stack+intern", "tags": ["next.js", "python", "react"], "description": "next.js python react intern"},
    {"title": "Junior Software Engineer (sample)", "company": "StartupHub", "url": "https://remotive.com/remote-jobs?search=junior+software+engineer", "tags": ["python", "javascript"], "description": "junior software engineer python"},
    {"title": "Junior Backend Developer (sample)", "company": "APIFirst", "url": "https://remotive.com/remote-jobs?search=junior+backend+developer", "tags": ["python", "sql", "api"], "description": "junior backend python api sql"},
]


# ==========================================
# 2. Job search tools
# ==========================================

def score_job(job: dict) -> int:
    """Simple skill-overlap match score (0-100)."""
    blob = " ".join([job.get("title", ""), job.get("description", ""), " ".join(job.get("tags", []))]).lower()
    if not SKILLS:
        return 50
    hits = sum(1 for s in SKILLS if s in blob)
    return min(100, 40 + int(60 * hits / len(SKILLS)))


def clean_query(text: str) -> str:
    """Strip filler words, keep role/tech keywords. Preserves 'intern'/'junior' if present."""
    t = text.lower()
    # Check for internship intent BEFORE stripping keywords
    wants_intern = bool(re.search(r"\bintern(ship)?s?\b", t))
    wants_junior = bool(re.search(r"\bjunior\b", t))
    for w in ["find", "search", "show", "me", "get", "for", "jobs", "job",
              "internships", "internship", "please", "dhundo", "chahiye", "mujhe",
              "chahte", "hain", "karo", "lagao"]:
        t = re.sub(rf"\b{w}\b", " ", t)
    # Don't strip bare 'intern' or 'junior' if that's all that's left
    core = re.sub(r"\s+", " ", t).strip() or "python"
    return core, wants_intern or wants_junior


def fetch_jobs(query: str, limit: int = 5):
    """Live jobs from Remotive (no API key). Returns (jobs, is_live, header_note)."""
    q, wants_entry = clean_query(query)
    senior_words = ("senior", "lead", "principal", "staff", "head",
                    "director", "manager", "architect", "sr.", "tech lead", "vp ")
    entry_words = ("intern", "internship", "junior", "trainee",
                   "entry", "graduate", "fresher", "apprentice")

    # Build search terms — always prioritise entry-level
    if wants_entry:
        terms = [f"{q} intern", f"{q} junior", "intern", "junior", q]
    else:
        terms = [q, q.split(" ")[0], f"{q} developer", f"{q} engineer"]

    seen, jobs = set(), []
    for term in terms:
        if not term.strip():
            continue
        try:
            r = requests.get(REMOTIVE_URL, params={"search": term, "limit": 30}, timeout=HTTP_TIMEOUT)
            r.raise_for_status()
            raw = r.json().get("jobs", [])
        except Exception:
            raw = []
        for j in raw:
            url = j.get("url", "")
            if url in seen:
                continue
            seen.add(url)
            jobs.append({
                "title": j.get("title", ""),
                "company": j.get("company_name", ""),
                "url": url,
                "tags": [t.lower() for t in j.get("tags", [])],
                "description": re.sub(r"<[^>]+>", " ", j.get("description", ""))[:1500],
            })
        if len(jobs) >= 20:
            break

    if jobs:
        for j in jobs:
            title = j["title"].lower()
            j["match_score"] = score_job(j)
            j["entry"] = any(w in title for w in entry_words)
            j["is_senior"] = any(w in title for w in senior_words)

        # Remove senior roles — strictly for entry-level queries, loosely otherwise
        non_senior = [j for j in jobs if not j["is_senior"]]

        if non_senior:
            non_senior.sort(key=lambda j: (j["entry"], j["match_score"]), reverse=True)
            return non_senior[:limit], True, "live"
        elif not wants_entry:
            # User didn't ask for internships — show best senior results with a note
            jobs.sort(key=lambda j: j["match_score"], reverse=True)
            return jobs[:limit], True, "senior_only"
        else:
            # Wanted entry-level but only seniors found on Remotive → show sample
            pass

    # Fallback: API down OR only senior roles found for an entry-level search
    fallback = [dict(j, match_score=score_job(j)) for j in FALLBACK_JOBS]
    is_api_live = bool(jobs)  # True = API worked but had only seniors
    return fallback, False, "senior_filtered" if is_api_live else "api_down"



def build_draft(job: dict, start_date: str) -> dict:
    subject = f"Application: {job['title']} - {APPLICANT_NAME}"
    body = (
        f"Dear Hiring Team at {job['company']},\n\n"
        f"I am writing to apply for the {job['title']} position. "
        f"I am a B.Tech CSE student with hands-on experience in {', '.join(SKILLS[:4]) or 'software development'}, "
        f"and I am keen to contribute and learn on your team.\n\n"
        f"I can start from {start_date}.\n\n"
        + (f"{APPLICANT_LINKS}\n\n" if APPLICANT_LINKS else "")
        + f"Thank you for your time and consideration.\n\nRegards,\n{APPLICANT_NAME}"
    )
    return {
        "subject": subject, "body": body,
        "company": job["company"], "title": job["title"], "url": job.get("url", ""),
        "match_score": job.get("match_score", 0),
    }


def send_email(to_email: str, subject: str, body: str):
    """Sends via Resend. Returns (ok, message)."""
    if not RESEND_API_KEY:
        return False, "RESEND_API_KEY is not set in Agentverse Secrets."
    if not to_email:
        return False, "No recipient email. Reply 'confirm your@email.com' or set APPLY_TO_EMAIL."
    try:
        r = requests.post(
            "https://api.resend.com/emails",
            headers={"Authorization": f"Bearer {RESEND_API_KEY}", "Content-Type": "application/json"},
            json={"from": "Job Auto Applier <onboarding@resend.dev>", "to": [to_email], "subject": subject, "text": body},
            timeout=HTTP_TIMEOUT,
        )
        if r.status_code in (200, 201):
            return True, f"Email sent to {to_email}."
        return False, f"Email provider error {r.status_code}: {r.text[:200]}"
    except Exception as e:
        return False, f"Email failed: {e}"


# ==========================================
# 3. Recruiter Simulation (3 personas, parallel LLM calls)
# ==========================================

PERSONAS = [
    ("HR Screener", "👔",
     "You scan quickly for keyword match with the job post, clear communication, professionalism, "
     "and culture fit. You reject generic, copy-paste applications."),
    ("Technical Lead", "🧑‍💻",
     "You judge skill match against the job requirements, relevance of projects, and technical depth. "
     "You want evidence, not adjectives."),
    ("Founder/CEO", "🚀",
     "You assess potential, ownership, hunger to learn and growth mindset. You like people who ship things "
     "and show initiative, even without much experience."),
]


def call_llm(system: str, user: str):
    """One ASI:One chat completion. Returns text or None."""
    if not ASI1_API_KEY:
        return None
    try:
        r = requests.post(
            ASI1_URL,
            headers={"Authorization": f"Bearer {ASI1_API_KEY}", "Content-Type": "application/json"},
            json={
                "model": ASI1_MODEL,
                "temperature": 0.4,
                "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
            },
            timeout=LLM_TIMEOUT,
        )
        r.raise_for_status()
        return r.json()["choices"][0]["message"]["content"]
    except Exception:
        return None


def parse_persona_json(text):
    if not text:
        return None
    m = re.search(r"\{.*\}", text, re.S)
    if not m:
        return None
    try:
        d = json.loads(m.group(0))
        return {
            "score": max(0, min(10, int(float(d.get("score", 5))))),
            "strengths": str(d.get("strengths", "")).strip()[:300],
            "concerns": str(d.get("concerns", "")).strip()[:300],
            "suggestion": str(d.get("suggestion", "")).strip()[:300],
        }
    except Exception:
        return None


def rule_based_persona(name: str, job: dict, draft: dict) -> dict:
    """Fallback when the LLM is unavailable. Keeps the demo alive."""
    blob = " ".join([job.get("title", ""), job.get("description", ""), " ".join(job.get("tags", []))]).lower()
    hits = [s for s in SKILLS if s in blob]
    missing = [s for s in SKILLS if s not in blob]
    company = job.get("company", "the company")
    if name == "HR Screener":
        return {
            "score": min(9, 4 + len(hits)),
            "strengths": f"Keyword match on: {', '.join(hits) or 'basic role fit'}. Polite, professional tone.",
            "concerns": "Opening paragraph is generic and could be sent to any company.",
            "suggestion": f"Name {company} and one specific thing about their product in the first two lines.",
        }
    if name == "Technical Lead":
        return {
            "score": min(9, 3 + len(hits) * 2),
            "strengths": f"Stack overlap: {', '.join(hits) or 'limited overlap'}.",
            "concerns": "No concrete project or result is mentioned, only a list of skills."
                        + (f" Job also hints at: {', '.join(missing[:2])}." if missing else ""),
            "suggestion": "Add one line: a project you built using the job's main tech and what it achieved.",
        }
    return {
        "score": 5 + (2 if APPLICANT_LINKS else 0) + (1 if job.get("entry") else 0),
        "strengths": "Shows willingness to learn and contribute at an early stage.",
        "concerns": "Nothing proves you ship things. Passion is claimed, not demonstrated."
                    if not APPLICANT_LINKS else "Good that links are included, but impact is not quantified.",
        "suggestion": "Lead with your best shipped project and one number (users, speed-up, stars).",
    }


def run_persona(args):
    persona, job, draft = args
    name, _icon, brief = persona
    system = (
        f"You are a {name} at a hiring company reviewing an internship application. {brief} "
        "Be honest, specific and short. Reply with ONLY a JSON object, no markdown, in this exact shape: "
        '{"score": <integer 0-10>, "strengths": "<one sentence>", "concerns": "<one sentence>", '
        '"suggestion": "<one concrete fix>"}'
    )
    user = (
        f"JOB TITLE: {job.get('title')}\nCOMPANY: {job.get('company')}\n"
        f"JOB DESCRIPTION: {job.get('description', '')[:1000]}\n\n"
        f"CANDIDATE BIO: {APPLICANT_BIO}\nCANDIDATE SKILLS: {', '.join(SKILLS)}\n\n"
        f"APPLICATION EMAIL:\n{draft['body']}"
    )
    parsed = parse_persona_json(call_llm(system, user))
    source = "AI"
    if not parsed:
        parsed = rule_based_persona(name, job, draft)
        source = "rules"
    parsed["persona"], parsed["icon"], parsed["source"] = name, _icon, source
    return parsed


def simulate_recruiters(job: dict, draft: dict) -> list:
    """3 personas evaluated in parallel."""
    with ThreadPoolExecutor(max_workers=3) as pool:
        return list(pool.map(run_persona, [(p, job, draft) for p in PERSONAS]))


def format_simulation(results: list) -> str:
    lines = ["🎭 Recruiter Simulation (3 reviewers, before you apply)\n"]
    for r in results:
        lines.append(
            f"{r['icon']} {r['persona']}: {r['score']}/10\n"
            f"   Strengths: {r['strengths']}\n"
            f"   Concerns: {r['concerns']}\n"
            f"   Suggestion: {r['suggestion']}\n"
        )
    avg = sum(r["score"] for r in results) / max(1, len(results))
    if avg >= 7.5:
        verdict = "Strong application. Send it."
    elif avg >= 5.5:
        verdict = "Decent, but one tweak from the suggestions above would lift it."
    else:
        verdict = "Weak as written. Improve it before sending."
    ai_note = "" if all(r["source"] == "AI" for r in results) else " (some reviews are rule-based, add ASI1_API_KEY for full AI reviews)"
    lines.append(f"Overall: {avg:.1f}/10. {verdict}{ai_note}")
    return "\n".join(lines)


# ==========================================
# 4. Tracker + Smart Follow-up Scheduler
# ==========================================

def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def fmt_date(iso: str) -> str:
    try:
        return datetime.fromisoformat(iso).strftime("%d %b")
    except Exception:
        return iso


def load(ctx: Context, key: str):
    raw = ctx.storage.get(key)
    return json.loads(raw) if raw else None


def save(ctx: Context, key: str, value):
    ctx.storage.set(key, json.dumps(value))


def register_user(ctx: Context, sender: str):
    users = load(ctx, "users") or []
    if sender not in users:
        users.append(sender)
        save(ctx, "users", users)


def load_apps(ctx: Context, sender: str) -> list:
    return load(ctx, f"apps_{sender}") or []


def save_apps(ctx: Context, sender: str, apps: list):
    save(ctx, f"apps_{sender}", apps)


def add_application(apps: list, draft: dict, simulation: list) -> dict:
    app_id = max([a["id"] for a in apps], default=0) + 1
    t0 = now_utc()
    app = {
        "id": app_id,
        "title": draft["title"],
        "company": draft["company"],
        "url": draft.get("url", ""),
        "subject": draft["subject"],
        "status": "applied",
        "applied_at": t0.isoformat(),
        "sim_avg": round(sum(r["score"] for r in simulation) / max(1, len(simulation)), 1) if simulation else None,
        "followups": [
            {"day": d, "due": (t0 + timedelta(days=d)).isoformat(), "state": "scheduled", "draft": None}
            for d in FOLLOWUP_DAYS
        ],
    }
    apps.append(app)
    return app


def find_app(apps: list, app_id: int):
    return next((a for a in apps if a["id"] == app_id), None)


def fetch_company_insight(company: str, title: str):
    """Day-7 value-add: latest Hacker News story mentioning the company (free, no key)."""
    name = re.sub(r"\(.*?\)", "", company).strip()
    for q in (name, title.split(" ")[0] if title else ""):
        if not q:
            continue
        try:
            r = requests.get(HN_SEARCH_URL, params={"query": q, "tags": "story", "hitsPerPage": 5}, timeout=HTTP_TIMEOUT)
            r.raise_for_status()
            for h in r.json().get("hits", []):
                if h.get("title") and (h.get("url") or h.get("objectID")):
                    link = h.get("url") or f"https://news.ycombinator.com/item?id={h['objectID']}"
                    return h["title"], link
        except Exception:
            continue
    return None


def build_followup(app: dict, day: int) -> dict:
    company, title = app["company"], app["title"]
    subject = f"Re: {app['subject']}"
    if day == 3:
        body = (
            f"Dear Hiring Team at {company},\n\n"
            f"I hope you are doing well. I applied for the {title} position a few days ago and wanted to "
            f"politely check whether you need anything further from me. I remain very interested in the role.\n\n"
            f"Thank you for your time.\n\nRegards,\n{APPLICANT_NAME}"
        )
    elif day == 7:
        insight = fetch_company_insight(company, title)
        if insight:
            hook = (
                f"While reading about the space {company} works in, I came across \"{insight[0]}\" ({insight[1]}) "
                f"and it made me even more excited about the {title} role."
            )
        else:
            hook = (
                f"I have been reading more about what {company} is building and it has made me even more "
                f"excited about the {title} role."
            )
        body = (
            f"Dear Hiring Team at {company},\n\n{hook}\n\n"
            f"If it helps, I would be glad to share a short sample of relevant work or complete a small task.\n\n"
            f"Regards,\n{APPLICANT_NAME}"
        )
    else:
        body = (
            f"Dear Hiring Team at {company},\n\n"
            f"This is my final follow-up regarding the {title} position. Since I applied, I have kept building; "
            f"my latest work is here:\n{APPLICANT_PORTFOLIO or '(portfolio link)'}\n\n"
            f"Thank you for considering my application. I would still love the opportunity to contribute.\n\n"
            f"Regards,\n{APPLICANT_NAME}"
        )
    return {"subject": subject, "body": body}


LABEL = {3: "Day 3 check-in", 7: "Day 7 value-add", 14: "Day 14 final follow-up"}


def release_due(apps: list) -> list:
    """Marks due follow-ups as ready, builds their drafts. Returns notification texts."""
    notes, t = [], now_utc()
    for app in apps:
        if app["status"] in CLOSED_STATUSES:
            for f in app["followups"]:
                if f["state"] in ("scheduled", "ready"):
                    f["state"] = "cancelled"
            continue
        for f in app["followups"]:
            if f["state"] == "scheduled" and datetime.fromisoformat(f["due"]) <= t:
                f["draft"] = build_followup(app, f["day"])
                f["state"] = "ready"
                notes.append(
                    f"⏰ {LABEL[f['day']]} ready for #{app['id']} {app['title']} at {app['company']}\n\n"
                    f"Subject: {f['draft']['subject']}\n\n{f['draft']['body']}\n\n"
                    f"Reply 'send followup {app['id']}' to send, or 'skip followup {app['id']}'."
                )
                break  # one follow-up at a time per application
    return notes


def ready_followup(app: dict):
    return next((f for f in app["followups"] if f["state"] == "ready"), None)


def next_followup_text(app: dict) -> str:
    if app["status"] in CLOSED_STATUSES:
        return "-"
    f = next((x for x in app["followups"] if x["state"] in ("ready", "scheduled")), None)
    if not f:
        return "all follow-ups done"
    if f["state"] == "ready":
        return f"{LABEL[f['day']]} READY (send followup {app['id']})"
    return f"{LABEL[f['day']]} on {fmt_date(f['due'])}"


def format_tracker(apps: list) -> str:
    if not apps:
        return "Tracker khali hai. Pehle internship dhundo aur apply karo."
    counts = {}
    for a in apps:
        counts[a["status"]] = counts.get(a["status"], 0) + 1
    summary = ", ".join(f"{v} {k}" for k, v in counts.items())
    lines = [f"📋 Application Tracker ({len(apps)} total: {summary})\n"]
    for a in apps:
        sim = f" | sim {a['sim_avg']}/10" if a.get("sim_avg") is not None else ""
        lines.append(
            f"#{a['id']} {a['title']} at {a['company']}\n"
            f"   Status: {a['status'].upper()} | applied {fmt_date(a['applied_at'])}{sim}\n"
            f"   Next: {next_followup_text(a)}"
        )
    lines.append("\nUpdate: 'update 1 interview' (applied/interview/offer/rejected/withdrawn)")
    return "\n".join(lines)


# ==========================================
# 5. Chat Protocol (required for ASI:One)
# ==========================================

chat_proto = Protocol(spec=chat_protocol_spec)


def make_msg(text: str) -> ChatMessage:
    return ChatMessage(
        timestamp=datetime.now(timezone.utc),
        msg_id=uuid4(),
        content=[TextContent(type="text", text=text)],
    )


HELP = (
    "Main internship dhundta hoon, application ko 3 recruiter personas se review karwata hoon, "
    "bhejta hoon (tumhari confirmation ke baad), aur smart follow-ups schedule karta hoon.\n\n"
    "Try karo:\n"
    "- find python internships\n"
    "- apply 2   (ya: apply 2 from 1 Jan 2027)\n"
    "- confirm   (ya: confirm you@email.com)\n"
    "- cancel\n"
    "- tracker\n"
    "- update 1 interview\n"
    "- followups / send followup 1 / skip followup 1\n"
    "- fastforward 3   (demo: 3 din aage)"
)


@chat_proto.on_message(ChatMessage)
async def handle_chat(ctx: Context, sender: str, msg: ChatMessage):
    await ctx.send(sender, ChatAcknowledgement(
        timestamp=datetime.now(timezone.utc),
        acknowledged_msg_id=msg.msg_id,
    ))

    text = " ".join(c.text for c in msg.content if isinstance(c, TextContent)).strip()
    low = text.lower()
    jobs_key, draft_key = f"jobs_{sender}", f"draft_{sender}"
    register_user(ctx, sender)

    try:
        # ---- tracker ----
        if re.match(r"^(tracker|track|status|my applications|applications|dashboard)\b", low):
            apps = load_apps(ctx, sender)
            notes = release_due(apps)
            save_apps(ctx, sender, apps)
            await ctx.send(sender, make_msg(format_tracker(apps)))
            for n in notes:
                await ctx.send(sender, make_msg(n))
            return

        # ---- update N status ----
        m = re.match(r"^update\s*#?(\d+)\s+(\w+)", low)
        if m:
            apps = load_apps(ctx, sender)
            app = find_app(apps, int(m.group(1)))
            status = m.group(2)
            if status in ("interviewing", "interviewed"):
                status = "interview"
            if status in ("rejection", "ghosted"):
                status = "rejected"
            if not app:
                await ctx.send(sender, make_msg("Yeh application number tracker mein nahi hai. 'tracker' bolo."))
                return
            if status not in VALID_STATUSES:
                await ctx.send(sender, make_msg(f"Status inme se ek do: {', '.join(VALID_STATUSES)}"))
                return
            app["status"] = status
            extra = ""
            if status in CLOSED_STATUSES:
                for f in app["followups"]:
                    if f["state"] in ("scheduled", "ready"):
                        f["state"] = "cancelled"
                extra = " Baaki follow-ups cancel kar diye."
            save_apps(ctx, sender, apps)
            await ctx.send(sender, make_msg(f"#{app['id']} {app['title']} at {app['company']} -> {status.upper()}.{extra}"))
            return

        # ---- fastforward N (demo) ----
        m = re.match(r"^(fastforward|fast-forward|ff|skip ahead)\s*(\d+)", low)
        if m:
            days = int(m.group(2))
            apps = load_apps(ctx, sender)
            if not apps:
                await ctx.send(sender, make_msg("Pehle koi application bhejo, phir fastforward chalega."))
                return
            for a in apps:
                a["applied_at"] = (datetime.fromisoformat(a["applied_at"]) - timedelta(days=days)).isoformat()
                for f in a["followups"]:
                    f["due"] = (datetime.fromisoformat(f["due"]) - timedelta(days=days)).isoformat()
            notes = release_due(apps)
            save_apps(ctx, sender, apps)
            await ctx.send(sender, make_msg(f"⏩ Demo mode: {days} din aage. " + ("Follow-ups ready hain:" if notes else "Abhi koi follow-up due nahi.")))
            for n in notes:
                await ctx.send(sender, make_msg(n))
            return

        # ---- followups (check due) ----
        if re.match(r"^(followups|follow-ups|follow ups|check followups)\b", low):
            apps = load_apps(ctx, sender)
            notes = release_due(apps)
            save_apps(ctx, sender, apps)
            if not notes:
                ready = [a for a in apps if ready_followup(a)]
                if ready:
                    notes = [f"Ready: " + ", ".join(f"#{a['id']}" for a in ready) + ". Use 'send followup N'."]
                else:
                    notes = ["Abhi koi follow-up due nahi. 'tracker' mein dekho kab hai."]
            for n in notes:
                await ctx.send(sender, make_msg(n))
            return

        # ---- send / skip followup N ----
        m = re.match(r"^(send|skip)\s+follow-?\s?up\s*#?(\d+)", low)
        if m:
            action, app_id = m.group(1), int(m.group(2))
            apps = load_apps(ctx, sender)
            app = find_app(apps, app_id)
            f = ready_followup(app) if app else None
            if not f:
                await ctx.send(sender, make_msg("Is application ka koi follow-up ready nahi hai. 'followups' try karo."))
                return
            if action == "skip":
                f["state"] = "skipped"
                save_apps(ctx, sender, apps)
                await ctx.send(sender, make_msg(f"{LABEL[f['day']]} skip kar diya."))
                return
            ok, info = send_email(APPLY_TO_EMAIL, f["draft"]["subject"], f["draft"]["body"])
            if ok:
                f["state"] = "sent"
                if app["status"] == "applied":
                    app["status"] = "followed_up"
                save_apps(ctx, sender, apps)
                await ctx.send(sender, make_msg(f"Done. {LABEL[f['day']]} sent. {info}"))
            else:
                await ctx.send(sender, make_msg(f"Email nahi gaya. {info}\nFollow-up safe hai, dobara try karo."))
            return

        # ---- confirm ----
        m = re.match(r"^(confirm|yes|haan|ha|send)\b\s*([\w.+-]+@[\w-]+\.[\w.-]+)?", low)
        if m:
            draft = load(ctx, draft_key)
            if not draft:
                await ctx.send(sender, make_msg("Abhi koi draft pending nahi hai. Pehle 'apply 1' jaisa kuch bolo."))
                return
            to_email = m.group(2) or APPLY_TO_EMAIL
            ok, info = send_email(to_email, draft["subject"], draft["body"])
            if ok:
                apps = load_apps(ctx, sender)
                app = add_application(apps, draft, draft.get("simulation", []))
                save_apps(ctx, sender, apps)
                save(ctx, draft_key, None)
                sched = "\n".join(f"   - {LABEL[f['day']]}: {fmt_date(f['due'])}" for f in app["followups"])
                await ctx.send(sender, make_msg(
                    f"Done. {info}\n({draft['title']} at {draft['company']})\n\n"
                    f"📋 Tracked as #{app['id']}. Smart follow-ups scheduled:\n{sched}\n\n"
                    "Main time aane par draft ke saath yaad dilaunga. 'tracker' se status dekho."
                ))
            else:
                await ctx.send(sender, make_msg(f"Email nahi gaya. {info}\nDraft safe hai, fix karke dobara 'confirm' bolo."))
            return

        # ---- cancel ----
        if re.match(r"^(cancel|no|nahi|stop)\b", low):
            save(ctx, draft_key, None)
            await ctx.send(sender, make_msg("Draft discard kar diya. Naya search karna ho toh bolo."))
            return

        # ---- apply N (recruiter simulation + draft) ----
        m = re.match(r"^apply\b\D*(\d+)(?:.*?\bfrom\s+(.+))?$", low)
        if m:
            jobs = load(ctx, jobs_key)
            if not jobs:
                await ctx.send(sender, make_msg("Pehle search karo, jaise: find python internships"))
                return
            idx = int(m.group(1)) - 1
            if not (0 <= idx < len(jobs)):
                await ctx.send(sender, make_msg(f"1 se {len(jobs)} ke beech ka number do."))
                return
            start = (m.group(2) or "").strip() or "as per your convenience"
            job = jobs[idx]
            draft = build_draft(job, start)

            await ctx.send(sender, make_msg("🎭 3 recruiters tumhari application review kar rahe hain..."))
            simulation = simulate_recruiters(job, draft)
            draft["simulation"] = simulation
            save(ctx, draft_key, draft)

            await ctx.send(sender, make_msg(format_simulation(simulation)))
            await ctx.send(sender, make_msg(
                f"Draft ready:\n\nSubject: {draft['subject']}\n\n{draft['body']}\n\n"
                "Bhejun? 'confirm' bolo (ya 'confirm email@x.com'), warna 'cancel'."
            ))
            return

        # ---- help ----
        if low in ("", "hi", "hello", "help", "hey", "namaste"):
            await ctx.send(sender, make_msg(HELP))
            return

        # ---- default: search ----
        jobs, live, note = fetch_jobs(text)
        save(ctx, jobs_key, jobs)
        lines = []
        for i, j in enumerate(jobs, 1):
            link = f"\n   {j['url']}" if j.get("url") else ""
            lines.append(f"{i}. {j['title']} at {j['company']} (match {j['match_score']}%){link}")
        if note == "live":
            header = "Yeh mile (Remotive se):"
        elif note == "senior_only":
            header = "⚠️ Sirf senior roles mile — entry-level abhi available nahi hain Remotive pe:"
        elif note == "senior_filtered":
            header = ("⚠️ Remotive pe abhi sirf senior roles mil rahe hain internship ke liye. "
                      "Yeh sample jobs dikha raha hoon (labelled):")
        else:
            header = "⚠️ Live API abhi down hai, sample data dikha raha hoon:"
        await ctx.send(sender, make_msg(
            f"{header}\n\n" + "\n".join(lines) + "\n\nApply karne ke liye bolo: apply 1"
        ))

    except Exception as e:
        ctx.logger.error(f"handler error: {e}")
        await ctx.send(sender, make_msg("Kuch gadbad ho gayi, ek baar dobara try karo."))


@chat_proto.on_message(ChatAcknowledgement)
async def handle_ack(ctx: Context, sender: str, msg: ChatAcknowledgement):
    pass


# ==========================================
# 6. Background scheduler: proactively pings users when a follow-up is due
# ==========================================

@agent.on_interval(period=900.0)
async def follow_up_scheduler(ctx: Context):
    for user in load(ctx, "users") or []:
        try:
            apps = load_apps(ctx, user)
            notes = release_due(apps)
            if notes:
                save_apps(ctx, user, apps)
                for n in notes:
                    await ctx.send(user, make_msg(n))
        except Exception as e:
            ctx.logger.error(f"scheduler error for {user}: {e}")


agent.include(chat_proto, publish_manifest=True)