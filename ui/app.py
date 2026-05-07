"""Streamlit UI for the Intelligent Email Agent."""

from __future__ import annotations

import httpx
import streamlit as st

API_BASE = "http://localhost:8000/api"


# ---------------------------------------------------------------------------
# API helpers
# ---------------------------------------------------------------------------

def api_get(path: str) -> dict | list:
    resp = httpx.get(f"{API_BASE}{path}", timeout=30)
    resp.raise_for_status()
    return resp.json()


def api_post(path: str) -> dict | list:
    resp = httpx.post(f"{API_BASE}{path}", timeout=60)
    resp.raise_for_status()
    return resp.json()


# ---------------------------------------------------------------------------
# Priority badge colours
# ---------------------------------------------------------------------------

_PRIORITY_COLOURS = {
    "critical": "#e74c3c",
    "high": "#e67e22",
    "normal": "#3498db",
    "low": "#95a5a6",
}

_CATEGORY_LABELS = {
    "meeting": "Meeting",
    "deadline": "Deadline",
    "info": "Info",
    "action-required": "Action Required",
    "spam": "Spam",
}


def _priority_badge(priority: str) -> str:
    colour = _PRIORITY_COLOURS.get(priority, "#999")
    return (
        f'<span style="background:{colour};color:#fff;padding:2px 8px;'
        f'border-radius:4px;font-size:0.85em;font-weight:600;">'
        f"{priority.upper()}</span>"
    )


def _category_badge(category: str) -> str:
    label = _CATEGORY_LABELS.get(category, category)
    return (
        f'<span style="background:#2c3e50;color:#ecf0f1;padding:2px 8px;'
        f'border-radius:4px;font-size:0.85em;">{label}</span>'
    )


# ---------------------------------------------------------------------------
# Page config
# ---------------------------------------------------------------------------

st.set_page_config(
    page_title="Email Agent",
    page_icon="",
    layout="wide",
)

# Minimal custom CSS — keep the Streamlit defaults mostly intact.
st.markdown(
    """
    <style>
    .email-row {
        padding: 0.6rem 0;
        border-bottom: 1px solid #333;
    }
    .email-subject {
        font-weight: 600;
        font-size: 1rem;
    }
    .email-meta {
        color: #888;
        font-size: 0.85rem;
    }
    </style>
    """,
    unsafe_allow_html=True,
)


# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------

with st.sidebar:
    st.title("Email Agent")
    st.caption("AI-powered email triage")

    st.divider()

    if st.button("Classify All Unclassified", use_container_width=True):
        with st.spinner("Classifying..."):
            try:
                results = api_post("/emails/classify-all")
                st.success(f"Classified {len(results)} email(s).")
            except httpx.HTTPError as exc:
                st.error(f"API error: {exc}")

    st.divider()

    filter_priority = st.multiselect(
        "Filter by priority",
        options=["critical", "high", "normal", "low"],
        default=[],
    )

    filter_category = st.multiselect(
        "Filter by category",
        options=list(_CATEGORY_LABELS.keys()),
        default=[],
        format_func=lambda c: _CATEGORY_LABELS.get(c, c),
    )


# ---------------------------------------------------------------------------
# Load emails
# ---------------------------------------------------------------------------

try:
    emails: list[dict] = api_get("/emails")
except httpx.ConnectError:
    st.error(
        "Cannot reach the API server. "
        "Make sure it is running on http://localhost:8000."
    )
    st.stop()


# Apply filters.
if filter_priority:
    emails = [
        e for e in emails
        if e.get("classification") and e["classification"]["priority"] in filter_priority
    ]

if filter_category:
    emails = [
        e for e in emails
        if e.get("classification") and e["classification"]["category"] in filter_category
    ]


# Sort: classified emails first (by priority severity), then unclassified.
_PRIORITY_ORDER = {"critical": 0, "high": 1, "normal": 2, "low": 3}


def _sort_key(e: dict) -> tuple:
    cls = e.get("classification")
    if cls:
        return (0, _PRIORITY_ORDER.get(cls["priority"], 9))
    return (1, 0)


emails.sort(key=_sort_key)


# ---------------------------------------------------------------------------
# Email list + detail
# ---------------------------------------------------------------------------

st.header("Inbox")

if not emails:
    st.info("No emails match the current filters.")
    st.stop()


for email in emails:
    cls = email.get("classification")
    draft = email.get("draft_reply")

    # Build the header line.
    badges = ""
    if cls:
        badges = f"{_priority_badge(cls['priority'])} {_category_badge(cls['category'])}"

    col_subject, col_badges = st.columns([3, 1])
    with col_subject:
        st.markdown(
            f"**{email['subject']}**  \n"
            f"<span class='email-meta'>From: {email['sender']}  &middot;  "
            f"{email['timestamp'][:16].replace('T', ' ')}</span>",
            unsafe_allow_html=True,
        )
    with col_badges:
        if badges:
            st.markdown(badges, unsafe_allow_html=True)

    with st.expander("Details", expanded=False):
        st.text(email["body"])

        action_cols = st.columns(3)

        with action_cols[0]:
            if st.button("Classify", key=f"cls-{email['id']}"):
                with st.spinner("Classifying..."):
                    try:
                        result = api_post(f"/emails/{email['id']}/classify")
                        st.success(
                            f"{result['priority'].upper()} / "
                            f"{_CATEGORY_LABELS.get(result['category'], result['category'])}"
                        )
                        st.rerun()
                    except httpx.HTTPError as exc:
                        st.error(str(exc))

        with action_cols[1]:
            if cls and st.button("Draft Reply", key=f"draft-{email['id']}"):
                with st.spinner("Drafting..."):
                    try:
                        result = api_post(f"/emails/{email['id']}/draft")
                        st.rerun()
                    except httpx.HTTPError as exc:
                        st.error(str(exc))

        with action_cols[2]:
            if draft and st.button("Approve & Send", key=f"approve-{email['id']}"):
                with st.spinner("Sending..."):
                    try:
                        result = api_post(f"/emails/{email['id']}/approve")
                        st.success(f"Sent. Preview: {result['preview']}")
                        st.rerun()
                    except httpx.HTTPError as exc:
                        st.error(str(exc))

        if draft:
            st.divider()
            st.subheader("Draft Reply")
            st.text_area(
                "Reply body",
                value=draft["body"],
                height=150,
                key=f"body-{email['id']}",
                disabled=True,
            )
            if draft.get("pii_redacted"):
                st.warning(
                    f"PII redacted: {', '.join(draft['redacted_types'])}"
                )

        if cls:
            st.divider()
            st.caption(
                f"Confidence: {cls['confidence']:.0%} — {cls.get('reasoning', '')}"
            )

    st.markdown("<hr style='margin:0;border-color:#333;'>", unsafe_allow_html=True)
