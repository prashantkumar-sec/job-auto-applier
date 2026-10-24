# tracker_agent.py - AGENT 6: Tracker (Agentverse HOSTED). Keeps the application log, pushes rows to the
# Google Sheet webhook, and emails you a reminder for applications with no follow-up after N days.
# Secrets: SHEET_WEBHOOK_URL, SHEET_TOKEN (optional), RESEND_API_KEY + FOLLOWUP_EMAIL (for reminders),
#          FOLLOWUP_DAYS (optional, default 7), ALLOWED_SENDERS / MAIN_AGENT_ADDRESS (optional)
# Agentverse injects `agent`. Do NOT create Agent() or call run().
import asyncio
import json
import os
import time
from datetime import datetime, timezone

import requests
from uagents import Context, Model

MAIN_FALLBACK = "agent1q0yrr6d64f625r5e8j03qqh9qxq0naf0exwlqmppgsukanyj3pcrxj49dfs"


# ---- shared model: keep identical in every file that uses it ----
class TrackEvent(Model):
    user: str
    applicant: str
    company: str
    role: str
    location: str
    link: str
    to_email: str
    status: str
# ------------------------------------------------------------------


def allowed(sender: str) -> bool:
    ok = {a.strip() for a in os.getenv("ALLOWED_SENDERS", "").split(",") if a.strip()}
    ok.add(os.getenv("MAIN_AGENT_ADDRESS", "").strip() or MAIN_FALLBACK)
    return sender in ok


def load_rows(ctx):
    try:
        return json.loads(ctx.storage.get("rows") or "[]")
    except Exception:
        return []


def post_sheet(row):
    url = os.getenv("SHEET_WEBHOOK_URL", "")
    if not url:
        return
    try:
        requests.post(url, json=dict(row, token=os.getenv("SHEET_TOKEN", "")), timeout=12)
    except Exception:
        pass


@agent.on_message(model=TrackEvent)
async def on_track(ctx: Context, sender: str, msg: TrackEvent):
    if not allowed(sender):
        return
    row = {
        "date": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M"),
        "applicant": msg.applicant, "company": msg.company, "role": msg.role, "location": msg.location,
        "link": msg.link, "to": msg.to_email, "status": msg.status,
        "ts": time.time(), "user": msg.user, "reminded": False,
    }
    rows = load_rows(ctx)
    rows.append(row)
    ctx.storage.set("rows", json.dumps(rows[-300:]))
    await asyncio.to_thread(post_sheet, row)
    ctx.logger.info(f"tracked {msg.company} / {msg.role} [{msg.status}] (total {len(rows)})")


@agent.on_interval(period=24 * 60 * 60)
async def followups(ctx: Context):
    days = int(os.getenv("FOLLOWUP_DAYS", "7"))
    key, to = os.getenv("RESEND_API_KEY", ""), os.getenv("FOLLOWUP_EMAIL", "")
    rows, now = load_rows(ctx), time.time()
    due = [r for r in rows if r.get("status") == "Sent" and not r.get("reminded") and now - r.get("ts", now) >= days * 86400]
    ctx.logger.info(f"{len(due)} applications due for follow-up")
    if not due or not (key and to):
        return
    lines = [f"- {r['role']} at {r['company']} (applied {r['date']})  {r.get('link', '')}" for r in due]
    try:
        resp = await asyncio.to_thread(lambda: requests.post(
            "https://api.resend.com/emails",
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
            json={"from": os.getenv("RESEND_FROM", "Job Tracker <onboarding@resend.dev>"), "to": [to],
                  "subject": f"Follow up on {len(due)} application(s)",
                  "text": f"No reply for {days}+ days. Time for a polite follow-up:\n\n" + "\n".join(lines)},
            timeout=12))
        if resp.status_code in (200, 201):
            for r in due:
                r["reminded"] = True
            ctx.storage.set("rows", json.dumps(rows))
    except Exception:
        pass
