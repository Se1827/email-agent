"""Rule-based priority pre-pass — deterministic classification shortcuts.

Runs BEFORE the LLM classifier to:
  - Skip classification entirely for obvious spam/newsletters
  - Pre-set priority to HIGH for VIP senders
  - Pre-set priority to CRITICAL for urgent keywords

This avoids wasting LLM calls on emails that can be triaged with simple
pattern matching. Rules are loaded from ``data/rules.json`` (editable by
users) and from the sender_profiles database (VIP senders).

Zero LLM calls. Pure regex + pattern matching.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from src.models.email import Category, Email, Priority

log = logging.getLogger(__name__)


# ── Data classes ───────────────────────────────────────────────────────────


@dataclass
class RuleVerdict:
    """Result of running the rule engine on an email."""
    skip_llm: bool = False
    pre_priority: Optional[Priority] = None
    pre_category: Optional[Category] = None
    reasons: list[str] = field(default_factory=list)


@dataclass
class RulesConfig:
    """Parsed rules from data/rules.json."""
    vip_senders: list[str] = field(default_factory=list)
    urgent_keywords: list[str] = field(default_factory=list)
    spam_body_markers: list[str] = field(default_factory=list)
    spam_subject_markers: list[str] = field(default_factory=list)
    spam_sender_patterns: list[str] = field(default_factory=list)


# ── Module-level cache ────────────────────────────────────────────────────

_cached_config: RulesConfig | None = None
_cached_mtime: float = 0.0


def _load_rules(data_dir: Path) -> RulesConfig:
    """Load and cache rules from data/rules.json."""
    global _cached_config, _cached_mtime

    rules_path = data_dir / "rules.json"
    if not rules_path.exists():
        log.info("rules_file_not_found", extra={"path": str(rules_path)})
        return RulesConfig()

    try:
        mtime = rules_path.stat().st_mtime
        if _cached_config is not None and mtime == _cached_mtime:
            return _cached_config

        with open(rules_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        spam = data.get("spam_patterns", {})
        config = RulesConfig(
            vip_senders=[s.lower() for s in data.get("vip_senders", [])],
            urgent_keywords=data.get("urgent_keywords", []),
            spam_body_markers=spam.get("body_markers", []),
            spam_subject_markers=spam.get("subject_markers", []),
            spam_sender_patterns=spam.get("sender_patterns", []),
        )
        _cached_config = config
        _cached_mtime = mtime

        log.info(
            "rules_loaded",
            extra={
                "vip_count": len(config.vip_senders),
                "urgent_keywords": len(config.urgent_keywords),
                "spam_patterns": (
                    len(config.spam_body_markers)
                    + len(config.spam_subject_markers)
                    + len(config.spam_sender_patterns)
                ),
            },
        )
        return config
    except Exception:
        log.exception("rules_load_failed")
        return RulesConfig()


# ── Rule engine ────────────────────────────────────────────────────────────


def evaluate_rules(
    email: Email,
    data_dir: Path,
    *,
    db_vip_senders: list[str] | None = None,
) -> RuleVerdict:
    """Run all rules against an email and return a verdict.

    Parameters
    ----------
    email : Email
        The email to evaluate.
    data_dir : Path
        Path to the data directory containing rules.json.
    db_vip_senders : list[str] | None
        VIP senders from the database (sender_profiles), merged with
        the JSON config list.
    """
    config = _load_rules(data_dir)
    verdict = RuleVerdict()

    # Merge VIP lists (JSON config + database)
    all_vip = set(config.vip_senders)
    if db_vip_senders:
        all_vip.update(s.lower() for s in db_vip_senders)

    sender_lower = email.sender.lower()
    subject_lower = email.subject.lower()
    body_lower = email.body.lower()

    # ── 1. Spam / newsletter detection ─────────────────────────────────
    spam_score = 0
    spam_reasons: list[str] = []

    # Check sender patterns
    for pattern in config.spam_sender_patterns:
        if pattern.lower() in sender_lower:
            spam_score += 2
            spam_reasons.append(f"sender matches spam pattern: {pattern}")

    # Check body markers (strongest signal)
    for marker in config.spam_body_markers:
        if marker.lower() in body_lower:
            spam_score += 1
            spam_reasons.append(f"body contains: '{marker}'")

    # Check subject markers
    for marker in config.spam_subject_markers:
        if marker.lower() in subject_lower:
            spam_score += 2
            spam_reasons.append(f"subject contains: '{marker}'")

    # Threshold: 3+ spam signals → skip LLM
    if spam_score >= 3:
        verdict.skip_llm = True
        verdict.pre_priority = Priority.LOW
        verdict.pre_category = Category.SPAM
        verdict.reasons = spam_reasons[:5]  # Cap reasons
        log.info(
            "rule_engine_spam_detected",
            extra={
                "email_id": email.id,
                "spam_score": spam_score,
                "reasons": verdict.reasons,
            },
        )
        return verdict

    # ── 2. VIP sender check ────────────────────────────────────────────
    if all_vip:
        for vip in all_vip:
            if vip in sender_lower:
                verdict.pre_priority = Priority.HIGH
                verdict.reasons.append(f"VIP sender: {vip}")
                log.info(
                    "rule_engine_vip_detected",
                    extra={"email_id": email.id, "vip": vip},
                )
                break

    # ── 3. Urgent keyword check ────────────────────────────────────────
    combined_text = f"{subject_lower} {body_lower[:500]}"
    for keyword in config.urgent_keywords:
        if re.search(rf"\b{re.escape(keyword)}\b", combined_text, re.IGNORECASE):
            verdict.pre_priority = Priority.CRITICAL
            verdict.reasons.append(f"urgent keyword: '{keyword}'")
            log.info(
                "rule_engine_urgent_detected",
                extra={"email_id": email.id, "keyword": keyword},
            )
            break  # One urgent keyword is enough

    if verdict.reasons:
        log.info(
            "rule_engine_verdict",
            extra={
                "email_id": email.id,
                "skip_llm": verdict.skip_llm,
                "pre_priority": verdict.pre_priority.value if verdict.pre_priority else None,
                "pre_category": verdict.pre_category.value if verdict.pre_category else None,
                "reason_count": len(verdict.reasons),
            },
        )

    return verdict
