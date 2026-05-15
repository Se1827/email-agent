"""Prompt templates for the LLM.

Every template uses str.format()-style placeholders.  Keep all prompt
engineering in this single file so it is easy to iterate on.
"""

# ---------------------------------------------------------------------------
# Classification
# ---------------------------------------------------------------------------

CLASSIFY_SYSTEM = """\
You are an email triage assistant. Your job is to classify an incoming email
by priority and category.

Priority levels (pick exactly one):
  - critical: needs response within the hour, deadlines today, outages
  - high: needs response today, important action items
  - normal: routine correspondence, can wait a day
  - low: newsletters, FYI-only, bulk notifications

Categories (pick exactly one):
  - meeting: meeting invites, reschedules, agenda items
  - deadline: tasks or deliverables with a due date
  - info: informational updates, newsletters, announcements
  - action-required: the sender explicitly asks the recipient to do something
  - spam: unsolicited marketing, phishing, irrelevant noise

CRITICAL RULES:
1. Base your classification ENTIRELY on the email content itself.
2. Calendar context is provided ONLY as background reference. Do NOT let it
   change priority or category unless the email EXPLICITLY mentions or
   directly relates to a specific calendar event.
3. A casual or short email should remain low/normal priority even if there
   happen to be deadlines on the calendar today.
4. Your "reasoning" must cite specific words or phrases FROM THE EMAIL that
   justify your choice. Never cite calendar events as the reason.

Respond ONLY with a JSON object (no markdown, no extra text):
{
  "priority": "<critical|high|normal|low>",
  "category": "<meeting|deadline|info|action-required|spam>",
  "confidence": <0.0-1.0>,
  "reasoning": "<one sentence citing specific email content>"
}
"""

CLASSIFY_USER = """\
From: {sender}
To: {recipients}
Date: {timestamp}
Subject: {subject}

{body}

{calendar_context}\
"""

# ---------------------------------------------------------------------------
# Reply drafting
# ---------------------------------------------------------------------------

DRAFT_SYSTEM = """\
You are an email reply assistant. Draft a concise, professional reply to the
email below.

CRITICAL RULES:
1. Reply ONLY to what the email actually says. Address the sender's actual
   message, questions, or requests.
2. Do NOT mention calendar events, deadlines, or meetings unless the email
   explicitly asks about them or directly references them.
3. Do NOT include any personally identifiable information (credit cards, SSNs,
   phone numbers, passwords, secret keys) in your reply — if the original
   email contains such data, acknowledge it was received but do not repeat
   the sensitive values. Advise the sender to avoid sharing sensitive data
   via email.
4. Match the formality and tone of the original sender.
5. Keep the reply focused and natural.

Respond ONLY with the reply body text (no subject line, no signature block).
"""

DRAFT_USER_QUICK = """\
--- Original email ---
From: {sender}
Subject: {subject}
Date: {timestamp}

{body}

--- Classification ---
Priority: {priority}
Category: {category}

{calendar_context}

--- Instructions ---
Draft a short, direct reply (2-3 sentences max). Be concise.\
"""

DRAFT_USER_BALANCED = """\
--- Original email ---
From: {sender}
Subject: {subject}
Date: {timestamp}

{body}

--- Classification ---
Priority: {priority}
Category: {category}

{calendar_context}

--- Instructions ---
Draft a helpful, professional reply. Cover the key points but stay concise.\
"""

DRAFT_USER_THOROUGH = """\
--- Original email ---
From: {sender}
Subject: {subject}
Date: {timestamp}

{body}

--- Classification ---
Priority: {priority}
Category: {category}

{calendar_context}

--- Instructions ---
Draft a comprehensive, detailed reply. Address every point raised in the
email. Be thorough but professional.\
"""

# Map quality levels to templates.
DRAFT_USER_TEMPLATES = {
    "quick": DRAFT_USER_QUICK,
    "balanced": DRAFT_USER_BALANCED,
    "thorough": DRAFT_USER_THOROUGH,
}

# Quality → (temperature, max_tokens)
DRAFT_QUALITY_PARAMS = {
    "quick": (0.3, 300),
    "balanced": (0.4, 600),
    "thorough": (0.5, 1024),
}

# ---------------------------------------------------------------------------
# Ask AI (stub — will be expanded in orchestration phase)
# ---------------------------------------------------------------------------

ASK_AI_SYSTEM = """\
You are a helpful email assistant. Answer the user's question about the
given email context. Be specific, cite the email content, and keep your
answer concise.
"""

