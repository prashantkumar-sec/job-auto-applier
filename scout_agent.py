# scout_agent.py - AGENT 2: Scout (Agentverse HOSTED).
# Every 6h: sends JobQuery to the main agent (all queries in a burst) -> gets JobQueryResult
#           -> forwards to the Matcher agent (JobBatch) -> gets JobBatchRanked -> emails digest of NEW jobs.
# If MATCHER_ADDRESS is not set it skips ranking and works like before.
# Secrets: MAIN_AGENT_ADDRESS (optional, fallback hardcoded), MATCHER_ADDRESS, SCOUT_SKILLS ("python,react,sql"),
#          SCOUT_QUERIES ("role|kind|location;..."), SCOUT_DIGEST_EMAIL, RESEND_API_KEY
# Agentverse injects `agent`. Do NOT create Agent() or call run().
import asyncio
import json
import os

import requests
from uagents import Context, Model

DEFAULT_QUERIES = "python developer|internship|India;react developer|internship|Remote;backend developer|job|India"
PERIOD_SECONDS = 6 * 60 * 60
MAIN_FALLBACK = "agent1q0yrr6d64f625r5e8j03qqh9qxq0naf0exwlqmppgsukanyj3pcrxj49dfs"


# ---- shared models: keep identical in every file that uses them ----
class JobQuery(Model):
    query: str
    kind: str
    location: str


class JobQueryResult(Model):
    query: str
    source: str
    results_json: str


class JobBatch(Model):
    request_id: str
    query: str
    skills_json: str
    kind: str
    jobs_json: str


class JobBatchRanked(Model):
    request_id: str
    query: str
    jobs_json: str
# --------------------------------------------------------------------


def get_queries():
    out = []
    for part in os.getenv("SCOUT_QUERIES", DEFAULT_QUERIES).split(";"):
        bits = [b.strip() for b in part.split("|")]
        if len(bits) == 3 and bits[0]:
            out.append(tuple(bits))
    return out


@agent.on_interval(period=PERIOD_SECONDS)
async def send_queries(ctx: Context):
    main = os.getenv("MAIN_AGENT_ADDRESS", "").strip() or MAIN_FALLBACK
    qs = get_queries()
    ctx.logger.info(f"Scout sending {len(qs)} queries to main agent {main[:14]}...")
    await asyncio.gather(*(ctx.send(main, JobQuery(query=r, kind=k, location=l)) for r, k, l in qs))


def send_digest(new_jobs: list, query: str):
    key, to = os.getenv("RESEND_API_KEY", ""), os.getenv("SCOUT_DIGEST_EMAIL", "")
    if not (key and to and new_jobs):
        return
    lines = [f"- {j['title']} at {j['company']} ({j.get('location', '')}) match {j.get('match_score', '?')}%\n  {j.get('url', '')}"
             for j in new_jobs]
    try:
        requests.post(
            "https://api.resend.com/emails",
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
            json={"from": os.getenv("RESEND_FROM", "Job Scout <onboarding@resend.dev>"), "to": [to],
                  "subject": f"Job Scout: {len(new_jobs)} new for '{query}'",
                  "text": "New matches:\n\n" + "\n".join(lines)},
            timeout=12,
        )
    except Exception:
        pass


async def process(ctx: Context, query: str, source: str, jobs: list):
    seen = set(json.loads(ctx.storage.get("seen") or "[]"))
    new = [j for j in jobs if j.get("url") and j["url"] not in seen]
    seen.update(j["url"] for j in new)
    ctx.storage.set("seen", json.dumps(list(seen)[-500:]))
    ctx.storage.set("last_results", json.dumps({"query": query, "source": source, "jobs": jobs}))
    ctx.logger.info(f"{len(jobs)} jobs for '{query}' via {source}; {len(new)} new")
    for j in jobs[:5]:
        ctx.logger.info(f"  - {j.get('title')} at {j.get('company')} | {j.get('match_score', '-')}% | {j.get('url')}")
    await asyncio.to_thread(send_digest, new, query)


@agent.on_message(model=JobQueryResult)
async def on_results(ctx: Context, sender: str, msg: JobQueryResult):
    try:
        jobs = json.loads(msg.results_json)
    except Exception:
        jobs = []
    matcher = os.getenv("MATCHER_ADDRESS", "").strip()
    if not matcher:
        await process(ctx, msg.query, msg.source, jobs)
        return
    skills = [s.strip().lower() for s in os.getenv("SCOUT_SKILLS", "").split(",") if s.strip()]
    kind = {r: k for r, k, _ in get_queries()}.get(msg.query, "job")
    await ctx.send(matcher, JobBatch(request_id=msg.query, query=msg.query, skills_json=json.dumps(skills),
                                     kind=kind, jobs_json=msg.results_json))


@agent.on_message(model=JobBatchRanked)
async def on_ranked(ctx: Context, sender: str, msg: JobBatchRanked):
    if sender != os.getenv("MATCHER_ADDRESS", "").strip():
        return
    try:
        jobs = json.loads(msg.jobs_json)
    except Exception:
        jobs = []
    await process(ctx, msg.query, "matcher", jobs)
