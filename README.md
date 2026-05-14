# Intelligent Email Agent

AI-powered email triage: classifies emails by priority and category, drafts context-aware replies, highlights urgent items, and lets you approve before sending. Built with FastAPI, React, and Groq (Llama 3.3 70B).

## Prerequisites

- Python 3.11+
- Node.js 18+
- A Groq API key (free tier works)

## Quickstart

```bash
# 1. Create a virtual environment and install Python deps
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# 2. Install frontend deps
cd frontend && npm install && cd ..

# 3. Configure environment
cp .env.example .env
# Edit .env and set your GROQ_API_KEY

# 4. Run (starts both API + React UI)
python run.py
```

The API runs at `http://localhost:8000`, the React UI at `http://localhost:5173`.

```bash
# Other run modes:
python run.py --api-only         # API server only
python run.py --ui=streamlit     # legacy Streamlit UI on :8501
```

## Project Structure

```
src/
  config.py            – settings from .env
  models/email.py      – Pydantic data models
  connectors/
    mock.py            – loads seed emails from JSON
    imap.py            – real IMAP mailbox connector
  llm/
    client.py          – async Groq wrapper
    prompts.py         – all prompt templates
  services/
    classifier.py      – priority + category via LLM
    drafter.py         – context-aware reply via LLM
    calendar.py        – mock calendar context
    pii.py             – configurable privacy gateway for regex, lazy semantic, or strict Presidio masking
  storage.py           – encrypted PostgreSQL app storage (optional async writer)
  observability.py     – OpenTelemetry setup and span helpers
  api/
    app.py             – FastAPI factory
    routes.py          – API endpoints
  logging.py           – structured JSON logging

frontend/src/          – React email client UI (Vite)
ui/app.py              – legacy Streamlit dashboard
data/                  – seed emails + mock calendar
eval/                  – golden dataset + evaluation script
tests/                 – pytest unit tests
```

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/emails` | List all emails |
| GET | `/api/emails/{id}` | Single email detail |
| POST | `/api/emails/{id}/classify` | Classify one email |
| POST | `/api/emails/{id}/draft` | Draft a reply |
| POST | `/api/emails/{id}/approve` | Approve and send (simulated) |
| POST | `/api/emails/classify-all` | Batch classify |
| POST | `/api/emails/refresh` | Re-fetch emails from source |
| GET | `/api/calendar` | Mock calendar events |

## Connecting a Real Email Account

Set `EMAIL_SOURCE=imap` in your `.env` and fill in the IMAP fields — same settings you would use in Thunderbird:

```env
EMAIL_SOURCE=imap
IMAP_HOST=imap.gmail.com
IMAP_PORT=993
IMAP_USER=you@gmail.com
IMAP_PASS=your-app-password
IMAP_MAILBOX=INBOX
IMAP_USE_SSL=true
IMAP_FETCH_LIMIT=20
```

For **Gmail**, you need an [App Password](https://myaccount.google.com/apppasswords) (not your regular password). For **Outlook**, use `imap-mail.outlook.com:993`. Any provider that supports standard IMAP will work.

## Tests

```bash
# Unit tests (no API key needed — LLM is mocked)
python -m pytest tests/ -v

# Offline full pipeline evaluation (LLM mocked, PII/prompt/draft checks active)
python eval/evaluate.py

# Live evaluation against the configured model
python eval/evaluate.py --live

# Include an explicit encrypted PostgreSQL write probe
python eval/evaluate.py --live --storage-probe
```

## Storage and Observability

Encrypted PostgreSQL storage is optional and off by default. When enabled, the app stores full emails, calendar events, workflow events, LLM prompts/responses, approvals, and evaluation artifacts. Searchable metadata stays small and non-sensitive; full payloads are encrypted with `STORAGE_ENCRYPTION_KEY` before insert. Runtime writes use a background queue so storage cannot slow down classification or drafting.

When storage is enabled, the API now hydrates email state from Postgres on load. Existing classifications and drafts are reused after a restart, so the LLM is not called again unless you explicitly force it:

```bash
POST /api/emails/{id}/classify?force=true
POST /api/emails/{id}/draft?force=true
```

Storage also keeps encrypted PII token mappings, compact thread state, semantic-memory records for future RAG/pgvector retrieval, and audit events for cache hits, classifications, drafts, approvals, and model calls.

For local Docker with pgvector:

```bash
docker volume create email_agent_pgdata

docker run --name email-agent-postgres \
  -e POSTGRES_USER=email_agent \
  -e POSTGRES_PASSWORD=email_agent \
  -e POSTGRES_DB=email_agent \
  -p 5432:5432 \
  -v email_agent_pgdata:/var/lib/postgresql/data \
  -d pgvector/pgvector:pg16
```

Then set:

```env
STORAGE_ENABLED=true
DATABASE_URL=postgresql://email_agent:email_agent@localhost:5432/email_agent
STORAGE_ENCRYPTION_KEY=<generated-fernet-key>
```

Storage admin helpers:

```bash
python scripts/storage_admin.py init
python scripts/storage_admin.py stats
python scripts/storage_admin.py wipe-email <email_id>
python scripts/storage_admin.py wipe-all
```

OpenTelemetry is optional and off by default. Set `OTEL_ENABLED=true` to instrument FastAPI and local spans. If `OTEL_EXPORTER_OTLP_ENDPOINT` is empty, spans go to console; otherwise they are exported over OTLP HTTP.

## PII Masking Modes

Set `PII_MODE` to control the privacy/latency tradeoff before anything is sent to the LLM:

| Mode | Behavior | Tradeoff |
|------|----------|----------|
| `strict_presidio` | Regex masking plus semantic detection on every prompt | Safest, slowest |
| `lazy_semantic` | Regex masking plus semantic detection only when sensitive context words appear | Faster, can miss ordinary names/places |
| `regex_only` | Regex masking only | Fastest, can miss names and other semantic PII |

Default is `strict_presidio`.

Evaluation writes two artifacts per run in `eval/reports/`: a Markdown report for human review and a JSON report for automation. Each case includes the input email, PII mappings, masked body, exact prompt sent to the LLM, raw LLM output, parsed classification, draft, privacy checks, and storage diagnostics. Live eval separates must-pass checks (classification + privacy + prompt capture) from review checks (draft wording), so correct model behavior is not marked failed just because the draft uses different phrasing.

## Adding a New Connector

1. Create a new module in `src/connectors/` (e.g. `graph.py`)
2. Implement a function that returns `list[Email]`
3. Add a new `EMAIL_SOURCE` option in `config.py` and `routes.py`

The rest of the pipeline (classification, drafting, PII redaction) works unchanged.

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `GROQ_API_KEY` | -- | Your Groq key |
| `GROQ_MODEL` | `llama-3.3-70b-versatile` | Chat model to use |
| `EMAIL_SOURCE` | `mock` | `mock` or `imap` |
| `IMAP_HOST` | -- | IMAP server address |
| `IMAP_PORT` | `993` | IMAP port |
| `IMAP_USER` | -- | Email address / username |
| `IMAP_PASS` | -- | Password or app password |
| `IMAP_MAILBOX` | `INBOX` | Folder to read |
| `IMAP_USE_SSL` | `true` | Use SSL/TLS |
| `IMAP_FETCH_LIMIT` | `20` | Max emails to fetch |
| `LOG_LEVEL` | `INFO` | Logging level |
| `API_PORT` | `8000` | FastAPI port |
| `UI_PORT` | `8501` | Streamlit port |
| `PII_MODE` | `strict_presidio` | `strict_presidio`, `lazy_semantic`, or `regex_only` masking mode |
| `STORAGE_ENABLED` | `false` | Enable encrypted PostgreSQL storage |
| `DATABASE_URL` | -- | PostgreSQL connection string |
| `STORAGE_ENCRYPTION_KEY` | -- | Fernet key for app-side payload encryption |
| `OTEL_ENABLED` | `false` | Enable OpenTelemetry tracing |
| `OTEL_SERVICE_NAME` | `email-agent` | Service name for traces |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | -- | Optional OTLP HTTP collector endpoint |
