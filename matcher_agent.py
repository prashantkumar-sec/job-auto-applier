# matcher_agent.py - AGENT 3: Matcher (Agentverse HOSTED). No LLM, no network = instant.
# Receives JobBatch, de-duplicates, drops senior roles for internships, ranks by skill match,
# replies JobBatchRanked.
# Secrets: ALLOWED_SENDERS (comma-separated agent addresses allowed to call it, e.g. the scout's address)
#          MAIN_AGENT_ADDRESS (optional, main agent is always allowed)
# Agentverse injects `agent`. Do NOT create Agent() or call run().
import json
import os

from uagents import Context, Model

MAIN_FALLBACK = "agent1q0yrr6d64f625r5e8j03qqh9qxq0naf0exwlqmppgsukanyj3pcrxj49dfs"
SENIOR = ("senior", "lead", "principal", "staff", "head", "director", "manager", "architect", "sr.")
ENTRY = ("intern", "junior", "trainee", "graduate", "fresher")


# ---- shared models: keep identical in every file that uses them ----
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


def allowed(sender: str) -> bool:
    ok = {a.strip() for a in os.getenv("ALLOWED_SENDERS", "").split(",") if a.strip()}
    ok.add(os.getenv("MAIN_AGENT_ADDRESS", "").strip() or MAIN_FALLBACK)
    return sender in ok


def rank(jobs, skills, kind, top):
    seen, out = set(), []
    for j in jobs:
        title = (j.get("title") or "").lower()
        key = j.get("url") or f"{title}|{(j.get('company') or '').lower()}"
        if not key or key in seen:
            continue
        seen.add(key)
        if kind == "internship" and any(w in title for w in SENIOR):
            continue
        blob = " ".join([title, (j.get("description") or ""), " ".join(j.get("tags") or [])]).lower()
        hits = sum(1 for s in skills if s and s in blob)
        score = 40 + int(60 * hits / max(1, min(len(skills), 8))) if skills else 50
        if any(w in title for w in ENTRY):
            score += 10
        if j.get("email"):
            score += 5
        j["match_score"] = min(100, score)
        out.append(j)
    out.sort(key=lambda x: x["match_score"], reverse=True)
    return out[:top]


@agent.on_message(model=JobBatch, replies=JobBatchRanked)
async def on_batch(ctx: Context, sender: str, msg: JobBatch):
    if not allowed(sender):
        ctx.logger.warning(f"blocked sender {sender[:14]}")
        return
    try:
        jobs = json.loads(msg.jobs_json)
        skills = [str(s).lower() for s in json.loads(msg.skills_json or "[]")]
    except Exception:
        jobs, skills = [], []
    ranked = rank(jobs, skills, msg.kind, int(os.getenv("MATCHER_TOP", "8")))
    ctx.logger.info(f"ranked {len(jobs)} -> {len(ranked)} for '{msg.query}'")
    await ctx.send(sender, JobBatchRanked(request_id=msg.request_id, query=msg.query, jobs_json=json.dumps(ranked)))
