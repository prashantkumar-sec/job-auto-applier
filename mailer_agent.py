# mailer_agent.py - AGENT 5: Mailer (Agentverse HOSTED). The ONLY agent that holds the Resend key.
# Safety: accepts requests only from the main agent, skips duplicates (same recipient+subject in 24h),
# and enforces a daily send limit.
# Secrets: RESEND_API_KEY (required), RESEND_FROM (optional), MAX_SENDS_PER_DAY (optional, default 20),
#          ALLOWED_SENDERS / MAIN_AGENT_ADDRESS (optional)
# Agentverse injects `agent`. Do NOT create Agent() or call run().
import asyncio
import hashlib
import json
import os
import re
import time

import requests
from uagents import Context, Model

MAIN_FALLBACK = "agent1q0yrr6d64f625r5e8j03qqh9qxq0naf0exwlqmppgsukanyj3pcrxj49dfs"
EMAIL_RE = re.compile(r"^[\w.+-]+@[\w-]+\.[\w.-]+$")


# ---- shared models: keep identical in every file that uses them ----
class SendRequest(Model):
    request_id: str
    user: str
    to_email: str
    subject: str
    body: str
    reply_to: str
    job_json: str
    test_mode: bool


class SendResult(Model):
    request_id: str
    user: str
    ok: bool
    info: str
    to_email: str
    job_json: str
    test_mode: bool
# --------------------------------------------------------------------


def allowed(sender: str) -> bool:
    ok = {a.strip() for a in os.getenv("ALLOWED_SENDERS", "").split(",") if a.strip()}
    ok.add(os.getenv("MAIN_AGENT_ADDRESS", "").strip() or MAIN_FALLBACK)
    return sender in ok


def send_email(to_email, subject, body, reply_to):
    key = os.getenv("RESEND_API_KEY", "")
    if not key:
        return False, "RESEND_API_KEY secret set nahi hai."
    payload = {"from": os.getenv("RESEND_FROM", "Job Auto Applier <onboarding@resend.dev>"),
               "to": [to_email], "subject": subject, "text": body}
    if reply_to:
        payload["reply_to"] = reply_to
    try:
        r = requests.post("https://api.resend.com/emails",
                          headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
                          json=payload, timeout=12)
        if r.status_code in (200, 201):
            return True, f"Email sent to {to_email}."
        hint = ""
        if r.status_code in (403, 422):
            hint = " (Resend free tier: bina verified domain ke sirf apne Resend email par bhej sakte ho. 'confirm me' se test karo.)"
        return False, f"Resend error {r.status_code}: {r.text[:160]}{hint}"
    except Exception as e:
        return False, f"Email failed: {e}"


@agent.on_message(model=SendRequest, replies=SendResult)
async def on_send(ctx: Context, sender: str, msg: SendRequest):
    if not allowed(sender):
        ctx.logger.warning(f"blocked sender {sender[:14]}")
        return

    def reply(ok, info):
        return SendResult(request_id=msg.request_id, user=msg.user, ok=ok, info=info,
                          to_email=msg.to_email, job_json=msg.job_json, test_mode=msg.test_mode)

    to = msg.to_email.strip()
    if not EMAIL_RE.match(to):
        await ctx.send(sender, reply(False, "Invalid recipient email."))
        return
    now = time.time()
    try:
        sent = {k: v for k, v in json.loads(ctx.storage.get("sent") or "{}").items() if now - v < 86400}
    except Exception:
        sent = {}
    key = hashlib.sha1(f"{to.lower()}|{msg.subject}".encode()).hexdigest()
    if not msg.test_mode:
        if key in sent:
            await ctx.send(sender, reply(True, f"Already sent to {to} in the last 24h, duplicate skipped."))
            return
        if len(sent) >= int(os.getenv("MAX_SENDS_PER_DAY", "20")):
            await ctx.send(sender, reply(False, "Daily send limit reached. Try again tomorrow."))
            return
    ok, info = await asyncio.to_thread(send_email, to, msg.subject, msg.body, msg.reply_to)
    if ok and not msg.test_mode:
        sent[key] = now
        ctx.storage.set("sent", json.dumps(sent))
    ctx.logger.info(f"send ok={ok} to={to}")
    await ctx.send(sender, reply(ok, info))
