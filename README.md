# Job Auto Applier

![tag:innovationlab](https://img.shields.io/badge/innovationlab-3D8BD3)
![tag:hackathon](https://img.shields.io/badge/hackathon-5F43F1)
![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)

> **Fetch-A-Thon 3.0 · ASI:One Agent Challenge — From Intent to Action**

**Job Auto Applier** is an AI agent built on [Fetch.ai's Agentverse](https://agentverse.ai) that transforms job hunting from a tedious manual process into a single conversation. It finds jobs, simulates recruiter feedback, drafts and sends application emails, and tracks follow-ups — all from an ASI:One chat.

---

## 🎯 The Problem

Job seekers — especially students and fresh graduates — spend hours per week:
- Manually searching multiple job boards
- Guessing whether their application is strong enough
- Writing emails from scratch for every role
- Forgetting to follow up (the #1 reason candidates miss opportunities)

**Job Auto Applier automates all of this**, keeping humans in control (every email requires explicit confirmation before it's sent).

---

## ✨ What it does

| Step | Command | What happens |
|------|---------|--------------|
| **1. Find jobs** | `find python internships` | Pulls live listings from Remotive API, scores them against your skills |
| **2. Apply** | `apply 2` | Simulates feedback from 3 recruiter personas using ASI:One LLM, then drafts a tailored email |
| **3. Send** | `confirm` | Sends the email via Resend **only after you confirm** |
| **4. Track** | `tracker` | Shows all applications, statuses, and next follow-up dates |
| **5. Follow up** | `followups` | Auto-drafts Day 3 check-in, Day 7 value-add, Day 14 final follow-up |

### Recruiter Simulation (unique feature)
Before every application, 3 AI personas review your draft:
- 👔 **HR Screener** — keyword match, professionalism, culture fit
- 🧑‍💻 **Technical Lead** — skill match, evidence vs. adjectives
- 🚀 **Founder/CEO** — growth mindset, initiative, shipped work

Each gives a score /10 with specific improvement suggestions. Falls back to rule-based logic if no API key is configured — so the demo never dies.

---

## 🚀 Try it in ASI:One

Open [ASI:One Chat](https://asi1.ai/chat) and search for **`@jobautoapplier`**

```text
find python internships
apply 2
confirm
tracker
followups
```

> **Live demo chat:** _(add your shared ASI:One conversation URL here)_

---

## 🏗️ Architecture

```
ASI:One (ACP chat)
       |
       ▼
Job Auto Applier  (agentverse_agent.py — hosted on Agentverse)
  ├── Remotive API  →  live job listings
  ├── ASI:One LLM  →  3-persona recruiter simulation
  ├── Resend API   →  confirmed email delivery
  ├── HN Algolia   →  Day-7 company insight (free, no key)
  └── Agentverse Storage  →  per-user application tracker
```

The repo also contains a **multi-agent local implementation** (`main_agent.py`, `scout_agent.py`, `matcher_agent.py`, `writer_agent.py`, `mailer_agent.py`, `tracher_agent.py`) where dedicated uAgents workers communicate via messages. The hosted `agentverse_agent.py` is a consolidated, standalone version for Agentverse.

---

## 📦 Agent Directory

| File | Role | Agentverse Address |
|------|------|--------------------|
| `agentverse_agent.py` | Main hosted agent — ASI:One chat, search, simulation, email, tracker | _(add your Agentverse profile URL)_ |
| `main_agent.py` | Local multi-agent orchestrator | _(add if deployed)_ |
| `scout_agent.py` | Periodic job search + digest | _(add if deployed)_ |
| `matcher_agent.py` | Skill-based job ranking / de-duplication | _(add if deployed)_ |
| `writer_agent.py` | Tailored email draft generation | _(add if deployed)_ |
| `mailer_agent.py` | Confirmed email delivery with duplicate protection | _(add if deployed)_ |
| `tracher_agent.py` | Application tracker + Google Sheets webhook | _(add if deployed)_ |

---

## 🔧 Deploying to Agentverse

`agentverse_agent.py` is written for the **Agentverse hosted editor** — Agentverse injects the `agent` object. Do **not** run it as a standalone script.

### Steps
1. Sign in to [Agentverse](https://agentverse.ai)
2. Create a new **Hosted Agent**
3. Paste the full contents of `agentverse_agent.py` into the editor
4. Add secrets in the agent's **Secrets** settings (see table below)
5. Click **Run** — the agent will start and register on the network
6. Enable **ASI:One discoverability** in the agent settings
7. Test via [ASI:One Chat](https://asi1.ai/chat) by searching `@jobautoapplier`

### Secrets

| Secret key | Required | Purpose |
|-----------|----------|---------|
| `RESEND_API_KEY` | ✅ For email | From [resend.com](https://resend.com) free tier |
| `APPLY_TO_EMAIL` | ✅ For email | Destination email (on free tier: your verified address) |
| `ASI1_API_KEY` | Optional | Powers AI recruiter personas; rule-based fallback is built-in |
| `APPLICANT_NAME` | Optional | Your name (default: `Prashant`) |
| `APPLICANT_SKILLS` | Optional | Comma-separated: `python,react,sql` |
| `APPLICANT_LINKS` | Optional | Links shown in application emails |
| `APPLICANT_PORTFOLIO` | Optional | Portfolio URL for Day-14 follow-up |
| `APPLICANT_BIO` | Optional | 1–3 line bio for recruiter simulation context |

> ⚠️ Never put real API keys in README, source code, or screenshots. Rotate any key that has been exposed.

---

## 🧪 Local Setup (multi-agent version)

```bash
git clone https://github.com/YOUR_USERNAME/job-auto-applier
cd job-auto-applier
cp .env.example .env      # Fill in your keys
python -m venv venv
venv\Scripts\activate     # Windows
pip install uagents requests
python main_agent.py
```

---

## ✅ Fetch-A-Thon 3.0 Submission Checklist

- [x] Agentverse hosted agent (`agentverse_agent.py`)
- [x] ACP Chat Protocol with `publish_manifest=True`
- [x] ASI:One discoverable as `@jobautoapplier`
- [x] Full conversation-based workflow (find → apply → confirm → track → follow-up)
- [x] Public GitHub repository
- [ ] **ASI:One shared chat URL** — _(add link here)_
- [ ] **Agentverse profile URL** — _(add link here)_
- [ ] **Demo video (3–5 min)** — _(add link here)_
- [x] Tagged `innovationlab` + `hackathon` in Agentverse profile
- [x] Rule-based fallback (demo works without ASI1_API_KEY)
- [x] Email requires explicit user confirmation before sending

---

## 📝 Privacy & Safety

- Application state is stored in Agentverse hosted storage per-user
- Email is sent only after explicit `confirm` — never automatically
- No personal data is stored beyond what you provide in secrets and chat
- Use test data during demos; avoid sending to real recruiters with sample jobs

---

## 📄 License

[MIT](LICENSE) © 2026 Prashant Kumar
