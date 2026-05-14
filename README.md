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
    pii.py             – Presidio/spaCy privacy gateway + semantic masking
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

# Evaluation against golden dataset (needs API key)
python eval/evaluate.py
```

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
