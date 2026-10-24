# Job Auto Applier

![tag:innovationlab](https://img.shields.io/badge/innovationlab-3D8BD3)
![tag:hackathon](https://img.shields.io/badge/hackathon-5F43F1)

Job Auto Applier is a Fetch.ai agent that helps job seekers find relevant roles, rehearse an application with simulated recruiter feedback, prepare an application email, and track follow-ups from an ASI:One conversation.

> **Competition:** Fetch-A-Thon 3.0 — ASI:One Agent Challenge: From Intent to Action. The event brief requires an Agentverse agent, ACP support, ASI:One discoverability, a complete conversation-based workflow, and a public repository. See the [official hackpack](https://www.fetch.ai/events/hackathons/fetch-a-thon-3/hackpack) for the current requirements and submission steps.

## What it does

The current hosted demo is `agentverse_agent.py`. Its chat flow supports:

1. Search for internships or jobs using Remotive's live job API, with a labelled sample-job fallback if the API is unavailable.
2. Rank results against configured applicant skills.
3. Run a simulated review using three recruiter personas, using ASI:One when configured and rule-based feedback otherwise.
4. Draft an application email and send it to the configured destination only after the user confirms.
5. Track application status and schedule Day 3, Day 7, and Day 14 follow-up drafts.

Example ASI:One conversation:

```text
@jobautoapplier
find python internships
apply 2
confirm
tracker
followups
```

Find the main agent in [ASI:One Chat](https://asi1.ai/chat) by searching for or mentioning **`@jobautoapplier`**. The shared chat URL for a completed end-to-end demo should still be added below for judges.

The multi-file agent implementation is also present: `main_agent.py`, `scout_agent.py`, `matcher_agent.py`, `writer_agent.py`, `mailer_agent.py`, and `tracher_agent.py` (tracker). The hosted `agentverse_agent.py` is a separate, consolidated implementation; it is not a launcher for those worker files.

## Agent overview

| Agent / file | Responsibility | Address |
| --- | --- | --- |
| Job Auto Applier / `agentverse_agent.py` | ASI:One chat, job search, recruiter simulation, draft/confirmation, tracker and follow-ups | Discover as `@jobautoapplier` in [ASI:One](https://asi1.ai/chat); add Agentverse profile URL |
| Main / `main_agent.py` | Alternate chat agent with resume/profile handling and optional worker delegation | Add deployed Agentverse address |
| Scout / `scout_agent.py` | Periodically requests job searches and sends new-match digests | Add deployed Agentverse address |
| Matcher / `matcher_agent.py` | De-duplicates and ranks job batches by skills | Add deployed Agentverse address |
| Writer / `writer_agent.py` | Generates tailored email drafts | Add deployed Agentverse address |
| Mailer / `mailer_agent.py` | Sends confirmed emails with duplicate and daily-send protections | Add deployed Agentverse address |
| Tracker / `tracher_agent.py` | Records applications and can post to a Google Sheets webhook | Add deployed Agentverse address |

Only list agents that are actually deployed in your submission. Replace the address placeholders above with the public Agentverse profile links and agent addresses before submitting.

## Architecture

```text
ASI:One (ACP chat)
       |
       v
Job Auto Applier
  |-- Remotive job search + skill matching
  |-- ASI:One recruiter-persona simulation (rule-based fallback)
  |-- Email draft -> explicit user confirmation -> Resend
  |-- Per-user application tracker + scheduled follow-ups
```

The separate multi-agent implementation uses uAgents messages to connect the main, scout, matcher, writer, mailer, and tracker workers. Configure and deploy that architecture separately; it is not automatically started by the consolidated hosted file.

## Deploy the hosted ASI:One agent

`agentverse_agent.py` is written for the Agentverse hosted editor: Agentverse injects the `agent` object. Paste the file into a hosted agent, configure its secrets, publish the chat protocol manifest, then verify that the agent is discoverable and usable in ASI:One. Do not run this hosted file as a standalone Python script.

The source imports `uagents`, `uagents_core`, and `requests`. For local experiments, install compatible versions of those packages in a Python environment; this repository currently has no pinned dependency file or local runner. Deployment on Agentverse manages the hosted runtime.

### Hosted secrets

Set secrets in the Agentverse agent settings. Do not commit credentials or your `.env` file.

| Secret | Required | Purpose |
| --- | --- | --- |
| `ASI1_API_KEY` | Optional | Powers the recruiter-persona simulation; the code falls back to rule-based personas without it. |
| `RESEND_API_KEY` | Required to send email | Resend API credential. |
| `APPLY_TO_EMAIL` | Required to send email | Destination for confirmed application emails. For the Resend onboarding sender, Resend may restrict delivery to your own verified address. |
| `APPLICANT_NAME` | Optional | Applicant name; defaults to `Prashant` in the current source. |
| `APPLICANT_SKILLS` | Optional | Comma-separated skills used for job scoring. |
| `APPLICANT_LINKS` | Optional | Applicant links included in application drafts. |
| `APPLICANT_PORTFOLIO` | Optional | Portfolio link used in follow-up drafts; defaults to `APPLICANT_LINKS`. |
| `APPLICANT_BIO` | Optional | Short applicant description used by the recruiter simulation. |

Never put real API keys in this README, source control, screenshots, or demo video. Rotate any key that has been exposed.

## Other integrations

The consolidated agent uses the public Remotive API for live job listings. It uses the ASI:One API for simulated recruiter feedback and Resend for confirmed email delivery. The separate multi-file implementation has additional optional integrations, including Groq, SerpAPI, and a Google Sheets webhook; see the comments at the top of each source file for its configuration. Those variables do not all apply to `agentverse_agent.py`.

## Competition submission checklist

The official Fetch-A-Thon brief asks for the following deliverables. Fill in and verify these links before submitting through the ASI:One dashboard:

- [ ] Public GitHub repository (this repository)
- [ ] Public ASI:One shared chat showing the complete workflow: **add link**
- [ ] Agentverse profile URL(s) and deployed agent address(es): **add link(s)**
- [ ] 3–5 minute demo video: **add link**
- [ ] Short problem, target-user, and outcome description
- [ ] Confirm all agents are categorized under Innovation Lab and tagged for the hackathon
- [ ] Test the deployed flow, including the email confirmation and fallback behavior

The README badges above are the tags specified in the official hackpack. The source includes an ACP chat protocol manifest, but Agentverse registration, public discovery, deployment URLs, the shared chat, and demo video are deployment/submission facts that must be verified and supplied by the project owner. This README does not claim those steps are complete.

## Privacy and email safety

Use test data while demonstrating. Confirm the recipient and review the draft before sending. The hosted demo stores application state in Agentverse storage and may send applicant/job details to configured external services (ASI:One and Resend). Do not upload sensitive personal information unless you are comfortable with those services processing it.

## License

No license file is currently included. Add a license before granting permission for others to reuse or redistribute this project.
