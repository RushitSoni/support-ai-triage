# AI-Powered Customer Support Triage & Auto-Resolution System

An end-to-end AI ticket triage system built with n8n, Groq (OpenAI-compatible LLM API), Qdrant, and Postgres — featuring RAG-grounded response generation, schema-enforced structured outputs, human-in-the-loop escalation, PII redaction, a cost circuit breaker, and a closed-loop feedback pipeline.

## Problem & Solution

Support teams drown in repetitive tickets that could be answered from existing documentation, while genuinely risky or ambiguous tickets need a human's attention immediately. This system automatically classifies incoming tickets, retrieves relevant knowledge-base content, drafts a grounded reply, and routes each ticket to one of three outcomes — auto-resolve, draft-for-human-review, or escalate — based on confidence and risk, never on confidence alone.

## Architecture

```
Webhook (webform intake)
  → Normalize → Dedup check → PII Redaction → Budget/rate-limit circuit breaker
  → Insert ticket (Postgres)
  → Classify (Groq, forced JSON schema: category/urgency/sentiment/confidence/risk_flag)
  → Hard-coded risk override (billing/angry sentiment always forces human review)
  → Embed ticket (local embedding microservice) → Vector search (Qdrant, top-5)
  → Log retrieval context (Postgres) [parallel branch]
  → RAG-grounded draft reply (Groq, forced JSON schema, honest grounded:false fallback)
  → Decision engine (confidence + risk + groundedness thresholds)
  → Route: auto_resolve | draft_for_review | escalate
  → Send email (customer reply, or internal reviewer notification)
```

Three separate n8n workflows:
- **wf_ingestion** — the full pipeline above (intake through action)
- **wf_feedback_ingest** — logs human corrections/approvals against each decision
- **wf_monitoring_digest** — daily cron job emailing volume/accuracy metrics
- **wf_error_handler** — global error catcher, alerts on any node failure across all workflows

## Tech Stack

| Concern | Choice | Why |
|---|---|---|
| Orchestration | n8n (Docker) | Visual, inspectable, native Postgres/HTTP/Email nodes |
| Classification + drafting LLM | Groq (`openai/gpt-oss-120b`) | Free/fast, OpenAI-compatible structured output |
| Embeddings | Local `fastembed` (`BAAI/bge-small-en-v1.5`) via custom FastAPI microservice | No API cost, no external dependency |
| Vector DB | Qdrant (Docker) | Dedicated, fast, simple REST API |
| Relational DB | Postgres (Docker) | Tickets, classifications, decisions, outcomes, all queryable |
| Email | Gmail SMTP (app password) | Simplest reliable channel for a portfolio-scale deployment |
| Eval/CI | Custom Python `eval.py` + GitHub Actions | Regression-tests the classification prompt independent of n8n |

## Setup

1. `cp .env.example .env` and set a real Postgres password
2. `docker compose up -d --build` — starts Postgres, Redis, Qdrant, and the embedding microservice
3. Import the 4 workflow JSON files (in `/workflows`) into your own n8n instance
4. Add credentials in n8n: Postgres (host = container name, e.g. `support_ai_postgres`), an HTTP header/API-key credential for Groq, and Gmail SMTP
5. Run `cd kb_pipeline && pip install fastembed qdrant-client --break-system-packages && python3 embed_and_index.py` to index the sample KB corpus into Qdrant
6. Activate all 4 workflows in n8n
7. Open `webform/index.html`, point `WEBHOOK_URL` at your n8n instance, and submit a test ticket

## Eval Results

Run `cd eval && python3 eval.py` (requires `GROQ_API_KEY` set) against the 15-ticket hand-labeled eval set. This same script runs automatically in CI on any change to `eval/` or `kb_pipeline/` (see `.github/workflows/eval.yml`), tracking category accuracy, urgency accuracy, and — most importantly — the **false-negative rate on risk_flag**, since a risky ticket slipping through undetected is far more dangerous than a raw accuracy dip.

## What to Show in a Demo

1. The `wf_ingestion` canvas — walk through classification → RAG → decision branching live
2. A real ticket going in: structured classification JSON → retrieved KB context → the final routing decision
3. The deliberate failure cases: a risky billing/angry ticket forcing escalation even at high model confidence; an off-topic question correctly returning `grounded: false` instead of hallucinating
4. The PII redaction: a ticket containing a fake card number, showing `body_redacted` in Postgres with the number replaced before it ever reached the LLM
5. The budget circuit breaker: force-escalating tickets without calling the LLM at all when hourly volume exceeds a cap
6. The feedback loop: a logged outcome linked back to its original decision
7. The daily digest email with real volume/accuracy numbers

## Known Limitations & What I'd Do With More Time

- **Only webform ingestion is implemented.** Gmail/Slack ingestion were deliberately scoped out to focus depth-first on the classification → RAG → decision pipeline; the ingestion layer is designed to be channel-agnostic, so adding Gmail as a second trigger feeding the same normalize step would be straightforward.
- **No Slack interactive buttons.** Human review/approval currently happens via email notification rather than one-click Slack buttons. The decision engine's output is channel-agnostic by design, so Slack could be added as an alternative or additional action on the `draft_for_review`/`escalate` branches without touching the routing logic itself.
- **Thresholds are hardcoded in the Decision Engine node**, not yet read from the `config_thresholds` table, even though that table exists and is seeded. A production version would fetch and apply them dynamically so they can be tuned without redeploying.
- **PII redaction is regex-based**, not a proper NER model — it catches common patterns (emails, card-like numbers, phone numbers, SSNs) but would miss more creative formats. A dedicated PII-detection model would be more robust at scale.
- **The weekly prompt-tuning job from the roadmap (clustering misclassifications, auto-generating few-shot examples) was not built** — the feedback loop currently only logs outcomes; using that data to actually improve the prompt is the natural next step.
- **Rate limiting is a simple hourly ticket-count check**, not a true token/cost-based spend tracker against the LLM provider's actual billing.

## Repo Structure

```
support-ai-triage/
├── docker-compose.yml
├── .env.example
├── workflows/                  # exported n8n workflow JSON files
│   ├── wf_ingestion.json
│   ├── wf_feedback_ingest.json
│   ├── wf_monitoring_digest.json
│   └── wf_error_handler.json
├── db/
│   └── schema.sql
├── kb_pipeline/
│   ├── chunking.py
│   ├── embed_and_index.py
│   ├── query_test.py
│   ├── sample_docs/
│   └── sample_resolved_tickets.jsonl
├── embedding_service/
│   ├── app.py
│   ├── Dockerfile
│   └── requirements.txt
├── eval/
│   ├── eval_set.jsonl
│   └── eval.py
├── webform/
│   └── index.html
├── .github/workflows/eval.yml
└── README.md
```
