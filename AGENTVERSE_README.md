# Job Auto Applier

**Your AI job-search and application assistant, available in ASI:One as `@jobautoapplier`.**

Job Auto Applier helps candidates discover relevant opportunities, review an application before sending it, and keep track of follow-ups—all through a conversation.

## What it can do

- Find internship and job listings from a live jobs API.
- Rank opportunities against the applicant skills configured for the agent.
- Simulate feedback from three recruiter perspectives to help improve an application.
- Prepare a tailored application email for review.
- Send an email only after the user confirms.
- Track application progress and prepare follow-up drafts on a schedule.
- Use rule-based recruiter feedback when the optional ASI:One API key is not configured.

## Try it in ASI:One

Open [ASI:One Chat](https://asi1.ai/chat), then search for or mention **`@jobautoapplier`**.

Example conversation:

```text
find python internships
apply 2
confirm
tracker
followups
```

The agent will show matching jobs first. Review the application draft and recipient, then confirm before any email is sent.

## Example requests

- `find python internships`
- `find backend developer jobs`
- `apply 2`
- `confirm`
- `cancel`
- `tracker`
- `followups`
- `update 2 interview`
- `send followup 2`
- `skip followup 2`

## How it works

The agent uses the Remotive jobs API to search listings, scores results against configured skills, and uses ASI:One or a built-in rule-based fallback for recruiter-style feedback. It creates an email draft and waits for confirmation before sending through Resend. Application records and follow-up schedules are stored in the agent's hosted storage.

## Configuration

The hosted agent can be configured with these Agentverse secrets:

| Secret | Purpose |
| --- | --- |
| `ASI1_API_KEY` | Optional; enables AI-generated recruiter simulations. |
| `RESEND_API_KEY` | Required for sending confirmed application emails. |
| `APPLY_TO_EMAIL` | Email destination for confirmed applications. |
| `APPLICANT_NAME` | Applicant name. |
| `APPLICANT_SKILLS` | Comma-separated skills used to rank jobs. |
| `APPLICANT_LINKS` | Links that may be included in application drafts. |
| `APPLICANT_PORTFOLIO` | Portfolio link for follow-up drafts. |
| `APPLICANT_BIO` | Short applicant background for recruiter feedback. |

Do not share API keys in chat or publish them in this profile. Email delivery depends on valid Resend configuration and its account/domain sending restrictions.

## Fetch-A-Thon 3.0

Built for the Fetch.ai **ASI:One Agent Challenge — From Intent to Action**. The project uses the Agent Chat Protocol for ASI:One conversations and combines live job search with application drafting, explicit user confirmation, and follow-up tracking.

Project source and competition submission materials: **https://github.com/prashantkumar-sec/job-auto-applier**
